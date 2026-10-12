"""Owner mode: real tasks supplied by a human owner, results judged by that owner.

The agents never contact clients, never send results anywhere and never move
money. They draft solutions locally with the owner's models; the owner decides
what to deliver and records what the client actually paid. Those records are
what selection runs on.

A workspace is a directory::

    config.yaml     configuration used for this workspace
    state.json      population, economy totals, generation counter, RNG state
    tasks.json      every task and its status
    ledger.jsonl    append-only record of every money movement
    outbox/         one Markdown file per drafted result
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from .agent import Agent, Genome
from .config import Config, config_from_dict
from .economy import Economy
from .evolution import EvolutionEngine, GenerationEvents
from .market import Task, select_bid
from .population import Population
from .sandbox import Sandbox
from .solvers import LLMSolver

STATUSES = ("open", "in_review", "accepted", "rejected")
_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class WorkspaceError(RuntimeError):
    """Invalid workspace operation (missing workspace, unknown task, ...)."""


@dataclass
class OwnerTask:
    id: str
    category: str
    prompt: str
    price: float
    title: str = ""
    difficulty: float = 0.5
    check: dict[str, str] | None = None  # {"type": "exact" | "contains" | "regex", "value": ...}
    status: str = "open"
    agent_id: int | None = None
    bid: float | None = None
    cost: float | None = None
    seconds: float | None = None
    auto_check: bool | None = None
    paid: float | None = None
    generation: int | None = None
    output_file: str | None = None
    notes: list[str] = field(default_factory=list)

    @classmethod
    def from_spec(cls, spec: dict[str, Any]) -> OwnerTask:
        missing = [k for k in ("id", "category", "prompt", "price") if k not in spec]
        if missing:
            raise WorkspaceError(f"task {spec.get('id', '?')}: missing field(s) {missing}")
        task_id = str(spec["id"])
        if not _ID.match(task_id):
            raise WorkspaceError(f"task id {task_id!r}: use only letters, digits, '.', '_' and '-'")
        check = spec.get("check")
        if check in (None, "manual"):
            check = None
        elif not (isinstance(check, dict) and check.get("type") in ("exact", "contains", "regex")):
            raise WorkspaceError(f"task {task_id}: check must be manual or {{type: exact|contains|regex, value: ...}}")
        return cls(
            id=task_id,
            category=str(spec["category"]),
            prompt=str(spec["prompt"]),
            price=float(spec["price"]),
            title=str(spec.get("title", "")),
            difficulty=float(spec.get("difficulty", 0.5)),
            check=check,
        )

    def passes_check(self, output: str) -> bool | None:
        if self.check is None:
            return None
        kind, value = self.check["type"], str(self.check["value"])
        if kind == "exact":
            return output.strip() == value.strip()
        if kind == "contains":
            return value.lower() in output.lower()
        return re.search(value, output) is not None


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.cfg: Config
        self.population: Population
        self.economy: Economy
        self.sandbox: Sandbox
        self.tasks: dict[str, OwnerTask] = {}
        self.models: list[str] = []
        self.categories: list[str] = []
        self.generation = 0
        self.rng = random.Random()
        self._ledger_saved = 0

    # -- lifecycle -----------------------------------------------------------

    @classmethod
    def create(
        cls, root: str | Path, cfg: Config, models: list[str], categories: list[str], seed: int = 1
    ) -> Workspace:
        ws = cls(root)
        if (ws.root / "state.json").exists():
            raise WorkspaceError(f"{ws.root} already contains a workspace")
        ws.root.mkdir(parents=True, exist_ok=True)
        (ws.root / "outbox").mkdir(exist_ok=True)
        (ws.root / "config.yaml").write_text(yaml.safe_dump(cfg.to_dict(), sort_keys=False), encoding="utf-8")
        ws._setup(cfg)
        ws.models, ws.categories = list(models), list(categories)
        ws.rng = random.Random(seed)
        for _ in range(cfg.experiment.population_size):
            agent = ws.population.spawn(
                Genome.random(ws.categories, ws.models, ws.rng), reputation=cfg.economy.initial_reputation
            )
            ws.economy.fund(agent, cfg.economy.initial_budget, 0)
            agent.begin_generation()
        ws.save()
        return ws

    @classmethod
    def open(cls, root: str | Path) -> Workspace:
        ws = cls(root)
        state_path = ws.root / "state.json"
        if not state_path.exists():
            raise WorkspaceError(f"no workspace at {ws.root}; create one with: astra init --workspace {ws.root}")
        cfg = config_from_dict(yaml.safe_load((ws.root / "config.yaml").read_text(encoding="utf-8")))
        ws._setup(cfg)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        ws.population = Population.from_dict(state["population"])
        ws.economy.restore(state["economy"])
        ws.models, ws.categories = state["models"], state["categories"]
        ws.generation = state["generation"]
        version, internal, gauss = state["rng"]
        ws.rng.setstate((version, tuple(internal), gauss))
        tasks_path = ws.root / "tasks.json"
        if tasks_path.exists():
            for item in json.loads(tasks_path.read_text(encoding="utf-8")):
                ws.tasks[item["id"]] = OwnerTask(**item)
        return ws

    def _setup(self, cfg: Config) -> None:
        self.cfg = cfg
        self.sandbox = Sandbox(cfg.sandbox)
        self.economy = Economy(self.sandbox, keep_ledger=True)
        self.population = Population()

    def save(self) -> None:
        version, internal, gauss = self.rng.getstate()
        state = {
            "generation": self.generation,
            "models": self.models,
            "categories": self.categories,
            "economy": self.economy.state(),
            "population": self.population.to_dict(),
            "rng": [version, list(internal), gauss],
        }
        _atomic_write(self.root / "state.json", json.dumps(state, indent=1))
        _atomic_write(self.root / "tasks.json", json.dumps([asdict(t) for t in self.tasks.values()], indent=1))
        new = self.economy.ledger[self._ledger_saved:]
        if new:
            with open(self.root / "ledger.jsonl", "a", encoding="utf-8") as fh:
                for t in new:
                    fh.write(json.dumps(asdict(t)) + "\n")
            self._ledger_saved = len(self.economy.ledger)

    # -- tasks ---------------------------------------------------------------

    def add_tasks(self, path: str | Path) -> list[OwnerTask]:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        specs = data.get("tasks", []) if isinstance(data, dict) else data
        if not isinstance(specs, list):
            raise WorkspaceError(f"{path}: expected a list of tasks under 'tasks:'")
        added = []
        for spec in specs:
            task = OwnerTask.from_spec(spec)
            if task.id in self.tasks:
                raise WorkspaceError(f"task id {task.id!r} already exists in this workspace")
            self.tasks[task.id] = task
            added.append(task)
        new_categories = sorted({t.category for t in added} - set(self.categories))
        if new_categories:
            self.categories += new_categories
            for agent in self.population.all():
                agent.genome = agent.genome.with_categories(self.categories)
        self.save()
        return added

    def tasks_with_status(self, status: str) -> list[OwnerTask]:
        return [t for t in self.tasks.values() if t.status == status]

    # -- work ----------------------------------------------------------------

    def work(self, solver: LLMSolver, limit: int | None = None, progress: Callable[[str], None] | None = None) -> list[OwnerTask]:
        """Auction open tasks among living agents and draft results with the winners' models."""
        done = []
        load = {a.id: 0 for a in self.population.alive()}
        for owner_task in self.tasks_with_status("open")[:limit]:
            agents = [a for a in self.population.alive() if load.get(a.id, 0) < self.cfg.market.agent_capacity]
            if not agents:
                break
            task = Task(
                id=owner_task.id,
                generation=self.generation,
                category=owner_task.category,
                difficulty=owner_task.difficulty,
                size=1.0,
                max_price=owner_task.price,
                payload={"prompt": owner_task.prompt, "title": owner_task.title},
            )
            bids = [a.decide_bid(task, solver.estimate_cost(a, task), self.cfg.agent) for a in agents]
            bids = [b for b in bids if b is not None]
            if bids:
                bid, _ = select_bid(bids, task, self.rng)
                agent, bid_price = bid.agent, bid.price
            else:
                # Owner tasks must get done: fall back to the most focused agent that can pay.
                agent = max(agents, key=lambda a: (a.balance > 0, a.genome.focus.get(task.category, 0.0)))
                bid_price = None
                owner_task.notes.append("assigned without a bid")
            if progress is not None:
                progress(f"{owner_task.id}: agent {agent.id} ({agent.genome.model}) is drafting...")
            outcome = solver.produce(agent, task)
            self.economy.charge(agent, outcome.cost, "compute", self.generation, owner_task.id)
            owner_task.status = "in_review"
            owner_task.agent_id = agent.id
            owner_task.bid = bid_price
            owner_task.cost = outcome.cost
            owner_task.seconds = outcome.seconds
            owner_task.generation = self.generation
            owner_task.output_file = self._write_output(owner_task, agent, outcome.output)
            owner_task.auto_check = owner_task.passes_check(outcome.output)
            if owner_task.auto_check is False:
                self.review(owner_task.id, accepted=False, note="automatic check failed")
            load[agent.id] = load.get(agent.id, 0) + 1
            done.append(owner_task)
            self.save()
        return done

    def _write_output(self, task: OwnerTask, agent: Agent, output: str) -> str:
        path = self.root / "outbox" / f"{task.id}.md"
        g = agent.genome
        header = (
            f"<!-- task {task.id} | agent {agent.id} | model {g.model} | effort {g.effort:.2f} | "
            f"review {g.review} | compute cost {task.cost:.4f} | {task.seconds:.1f} s -->\n\n"
        )
        path.write_text(f"{header}# {task.title or task.id}\n\n{output}\n", encoding="utf-8")
        return str(path.relative_to(self.root))

    # -- review & evolution --------------------------------------------------

    def review(
        self, task_id: str, *, accepted: bool, paid: float | None = None, note: str = "", reopen: bool = False
    ) -> OwnerTask:
        """Record the owner's verdict and the money the client actually paid."""
        task = self.tasks.get(task_id)
        if task is None:
            raise WorkspaceError(f"unknown task {task_id!r}")
        if task.status != "in_review":
            raise WorkspaceError(f"task {task_id} is {task.status}, not in_review")
        agent = self.population.get(task.agent_id)
        if accepted:
            amount = task.price if paid is None else float(paid)
            self.economy.pay(agent, amount, self.generation, task.id)
            if not agent.alive:  # retired while waiting for review: the money goes to the owner
                self.economy.withdraw(agent, self.generation, "late payment")
            task.paid = amount
            task.status = "accepted"
        else:
            task.status = "rejected"
        agent.record_attempt(task.category, accepted, task.cost or 0.0, self.cfg.economy.reputation_alpha)
        if note:
            task.notes.append(note)
        if reopen and not accepted:
            retry = OwnerTask(
                id=_next_retry_id(task.id, self.tasks),
                category=task.category,
                prompt=task.prompt,
                price=task.price,
                title=task.title,
                difficulty=task.difficulty,
                check=task.check,
                notes=[f"retry of {task.id}"],
            )
            self.tasks[retry.id] = retry
        self.save()
        return task

    def close_generation(self) -> GenerationEvents:
        """Charge upkeep, close the books of this generation and run selection."""
        workers = self.population.alive()
        for agent in workers:
            self.economy.charge(agent, self.cfg.economy.upkeep, "upkeep", self.generation)
            agent.end_generation()
        engine = EvolutionEngine(
            self.cfg.evolution,
            self.sandbox,
            self.economy,
            self.models,
            self.rng,
            initial_reputation=self.cfg.economy.initial_reputation,
        )
        events = engine.step(self.population, self.generation)
        self.generation += 1
        for agent in self.population.alive():
            agent.begin_generation()
        self.save()
        return events

    # -- reporting -----------------------------------------------------------

    def status_text(self) -> str:
        alive = sorted(self.population.alive(), key=lambda a: -a.balance)
        counts = {s: len(self.tasks_with_status(s)) for s in STATUSES}
        revenue = sum(t.paid or 0.0 for t in self.tasks.values())
        compute = sum(t.cost or 0.0 for t in self.tasks.values())
        lines = [
            f"Workspace {self.root}  generation {self.generation}",
            f"Tasks: " + ", ".join(f"{k} {v}" for k, v in counts.items()),
            f"Money: allocated {self.economy.allocated:.2f}, revenue {revenue:.2f}, "
            f"compute {compute:.2f}, returned to owner {self.economy.returned:.2f}, "
            f"wealth {self.economy.wealth(self.population.all()):.2f}",
            "",
            f"{'agent':>5} {'specialty':<18} {'model':<28} {'effort':>6} {'review':>6} "
            f"{'balance':>9} {'rep':>5} {'done':>5} {'ok':>4}",
        ]
        for a in alive:
            g = a.genome
            lines.append(
                f"{a.id:>5} {g.specialty:<18} {g.model[:28]:<28} {g.effort:>6.2f} {str(g.review):>6} "
                f"{a.balance:>9.2f} {a.reputation:>5.2f} {a.tasks_done:>5} {a.tasks_succeeded:>4}"
            )
        return "\n".join(lines)


def _next_retry_id(task_id: str, tasks: dict[str, OwnerTask]) -> str:
    n = 1
    while f"{task_id}-r{n}" in tasks:
        n += 1
    return f"{task_id}-r{n}"


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
