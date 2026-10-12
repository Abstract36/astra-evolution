"""Experiment runner: several arms x several seeds over identical task streams.

Every arm of a given seed sees exactly the same tasks, so differences between
arms come from the agents' strategies, not from luck in the market.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from .agent import Agent, Bid, Genome
from .api_client import APIClient, ModelRouter
from .config import ARMS, BaselineConfig, Config, ConfigError, ModelSpec
from .economy import Economy
from .evolution import EvolutionEngine
from .market import RoundStats, SimulatedMarket, Task, WinModel, trade_round
from .ollama_client import OllamaClient, discover_models
from .population import Population, genome_stats
from .router import run_router_arm
from .sandbox import Sandbox
from .solvers import LLMSolver, Outcome, SimulatedSolver, Solver, api_call_cost, local_call_cost
from .verifiable import VerifiableMarket

Progress = Callable[[str], None]


class Market(Protocol):
    demand: dict[str, float]

    @property
    def categories(self) -> list[str]: ...

    def tasks_for(self, generation: int) -> list[Task]: ...


@dataclass
class ArmResult:
    arm: str
    seed: int
    initial_capital: float
    rows: list[dict[str, Any]] = field(default_factory=list)
    agents: list[dict[str, Any]] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    ledger: list[dict[str, Any]] = field(default_factory=list)


def tuned_genomes(baseline: BaselineConfig, demand: dict[str, float], n: int) -> list[Genome]:
    """A sensible human design: pure specialists, split across categories by demand."""
    quotas = {c: d * n for c, d in demand.items()}
    counts = {c: int(q) for c, q in quotas.items()}
    leftover = n - sum(counts.values())
    for c in sorted(quotas, key=lambda c: quotas[c] - counts[c], reverse=True)[:leftover]:
        counts[c] += 1
    genomes = []
    for category, count in counts.items():
        for _ in range(count):
            genomes.append(
                Genome(
                    focus={c: 1.0 if c == category else 0.0 for c in demand},
                    model=baseline.model,
                    effort=baseline.effort,
                    price_level=baseline.price_level,
                    max_difficulty=baseline.max_difficulty,
                    min_confidence=baseline.min_confidence,
                    review=baseline.review,
                )
            )
    return genomes


def run_arm(
    cfg: Config,
    arm: str,
    seed: int,
    genomes: list[Genome],
    market: Market,
    solver: Solver,
    models: list[str],
    *,
    log_attempts: bool = False,
    progress: Progress | None = None,
) -> ArmResult:
    _, evolve = ARMS[arm]
    sandbox = Sandbox(cfg.sandbox)
    economy = Economy(sandbox, keep_ledger=cfg.experiment.save_ledger)
    population = Population()
    for genome in genomes:
        agent = population.spawn(genome.copy(), reputation=cfg.economy.initial_reputation)
        economy.fund(agent, cfg.economy.initial_budget, 0)
    engine = EvolutionEngine(
        cfg.evolution,
        sandbox,
        economy,
        models,
        random.Random(seed * 1000 + 2),
        enabled=evolve,
        initial_reputation=cfg.economy.initial_reputation,
    )
    rng = random.Random(seed * 1000 + 1)
    win_model = WinModel(cfg.agent.prior_win_rate, cfg.agent.prior_weight)
    result = ArmResult(arm, seed, initial_capital=economy.allocated)

    def on_attempt(task: Task, bid: Bid, outcome: Outcome) -> None:
        result.attempts.append(attempt_record(arm, seed, task, bid.agent, bid.price, outcome))

    for generation in range(cfg.experiment.generations):
        tasks = market.tasks_for(generation)
        workers = population.alive()
        for agent in workers:
            agent.begin_generation()
        fees_before = economy.fees
        stats = trade_round(
            tasks,
            workers,
            solver,
            economy,
            cfg.agent,
            cfg.market,
            cfg.economy.reputation_alpha,
            rng,
            generation,
            on_attempt if log_attempts else None,
            cfg.economy.bid_cost,
            win_model,
        )
        for agent in workers:
            economy.charge(agent, cfg.economy.upkeep, "upkeep", generation)
        profits = [agent.end_generation() for agent in workers]
        events = engine.step(population, generation, stats.unserved, cfg.market.agent_capacity)
        row = _generation_row(arm, seed, generation, workers, profits, stats, cfg.economy.upkeep)
        row.update(
            {
                "spawn_fees": economy.fees - fees_before,
                "invested": events.invested,
                "treasury": economy.treasury,
                "wealth": economy.wealth(population.all()),
                "alive_after": len(population.alive()),
                "births": len(events.births),
                "bankrupt": len(events.bankrupt),
                "defunded": len(events.defunded),
                "outcompeted": len(events.outcompeted),
            }
        )
        row.update(genome_stats(workers, models, market.categories))
        row.update({f"demand:{c}": w for c, w in market.demand.items()})
        result.rows.append(row)
        if progress is not None and log_attempts:
            progress(
                f"  gen {generation}: agents {len(workers)}, succeeded {stats.succeeded}/{stats.assigned}, "
                f"profit {sum(profits):+.2f}, wealth {row['wealth']:.2f}"
            )

    result.agents = [_agent_record(a, arm, seed) for a in population.all()]
    result.ledger = [dict(arm=arm, seed=seed, **t) for t in economy.ledger_rows()]
    return result


def attempt_record(arm: str, seed: int, task: Task, agent: Agent, price: float, outcome: Outcome) -> dict[str, Any]:
    """One line of attempts.jsonl: what was tried, by whom, and what it cost."""
    expected = task.payload.get("answer")
    return {
        "arm": arm,
        "seed": seed,
        "generation": task.generation,
        "task": task.id,
        "category": task.category,
        "difficulty": round(task.difficulty, 3),
        "agent": agent.id,
        "model": agent.genome.model,
        "effort": round(agent.genome.effort, 3),
        "review": agent.genome.review,
        "price": round(price, 4),
        "success": outcome.success,
        "cost": round(outcome.cost, 4),
        "seconds": round(outcome.seconds, 3),
        "expected": expected if isinstance(expected, (str, int, float, list)) else None,
        "output": outcome.output[-500:],
    }


def _generation_row(
    arm: str,
    seed: int,
    generation: int,
    workers: list[Agent],
    profits: list[float],
    stats: RoundStats,
    upkeep: float,
) -> dict[str, Any]:
    n = len(workers)
    net = sum(profits)
    return {
        "arm": arm,
        "seed": seed,
        "generation": generation,
        "population": n,
        "tasks_offered": stats.offered,
        "tasks_assigned": stats.assigned,
        "tasks_succeeded": stats.succeeded,
        "lost_to_competitors": stats.lost_to_competitors,
        "tasks_unbid": stats.unbid,
        "revenue": stats.revenue,
        "compute_cost": stats.compute_cost,
        "sales_cost": stats.sales_cost,
        "upkeep": upkeep * n,
        "net_profit": net,
        "profit_per_agent": net / n if n else 0.0,
        "success_rate": stats.succeeded / stats.assigned if stats.assigned else 0.0,
        "market_share": stats.assigned / stats.offered if stats.offered else 0.0,
        "mean_reputation": sum(a.reputation for a in workers) / n if n else 0.0,
    }


def _agent_record(agent: Agent, arm: str, seed: int) -> dict[str, Any]:
    return {
        "arm": arm,
        "seed": seed,
        "id": agent.id,
        "parents": list(agent.parents),
        "born": agent.born,
        "died": agent.died,
        "death_reason": agent.death_reason,
        "children": agent.children,
        "generations_lived": len(agent.history),
        "balance": round(agent.balance, 4),
        "reputation": round(agent.reputation, 4),
        "lifetime_revenue": round(agent.lifetime_revenue, 4),
        "lifetime_cost": round(agent.lifetime_cost, 4),
        "tasks_done": agent.tasks_done,
        "tasks_succeeded": agent.tasks_succeeded,
        "genome": agent.genome.to_dict(),
    }


def _seed_genomes(cfg: Config, seed: int, categories: list[str], models: list[str], demand: dict[str, float]):
    rng = random.Random(seed * 1000 + 3)
    n = cfg.experiment.population_size
    return {
        "random": [Genome.random(categories, models, rng) for _ in range(n)],
        "tuned": tuned_genomes(cfg.baseline, demand, n),
    }


def run_experiment(cfg: Config, out_dir: str | Path | None = None, progress: Progress | None = None) -> dict:
    """The simulated experiment: every arm for every seed, then a summary."""
    from .results import summarize, write_results

    models = [m.name for m in cfg.models]
    solver = SimulatedSolver(cfg.models, cfg.economy)
    results = []
    for offset in range(cfg.experiment.seeds):
        seed = cfg.experiment.base_seed + offset
        probe = SimulatedMarket(cfg.market, random.Random(seed))
        start = _seed_genomes(cfg, seed, probe.categories, models, probe.demand)
        for arm in cfg.experiment.arms:
            market = SimulatedMarket(cfg.market, random.Random(seed))
            if ARMS[arm][0] == "menu":
                result = run_router_arm(cfg, seed, market, solver, models)
            else:
                result = run_arm(cfg, arm, seed, start[ARMS[arm][0]], market, solver, models)
            results.append(result)
            if progress is not None:
                final = result.rows[-1]
                progress(
                    f"seed {seed:>3}  {arm:<15} capital x{final['wealth'] / result.initial_capital:5.2f}  "
                    f"agents {final['alive_after']:>3}  last-gen profit {final['net_profit']:+8.2f}"
                )
    summary = summarize(results, cfg)
    if out_dir is not None:
        write_results(Path(out_dir), cfg, results, summary)
    return summary


def _verifiable_market(cfg: Config, seed: int) -> VerifiableMarket:
    competitor = cfg.market.competitor_price_range if cfg.market.external_competition else None
    return VerifiableMarket(
        cfg.ollama.categories, cfg.market.tasks_per_generation, random.Random(seed), competitor
    )


@dataclass
class ModelPool:
    """Every model the agents may choose from, cheapest first, behind one client."""

    client: ModelRouter
    names: list[str]
    costs: dict[str, float]  # first guess of credits per call, before experience
    api: APIClient | None
    descriptions: list[str]


def build_model_pool(
    cfg: Config, sandbox: Sandbox, local: Any | None = None, api: APIClient | None = None
) -> ModelPool:
    """Local Ollama models (if enabled) followed by paid API models (if enabled)."""
    infos = []
    if cfg.ollama.enabled:
        if local is None:
            local = OllamaClient(cfg.ollama.host, sandbox, cfg.sandbox.request_timeout)
        infos = discover_models(local, cfg.ollama.models, cfg.ollama.max_model_size_gb)
    if cfg.api.enabled and api is None:
        api = APIClient(cfg.api, sandbox)
    names = [m.name for m in infos]
    costs = {m.name: local_call_cost(m.size_gb, cfg.ollama.cost_per_second) for m in infos}
    descriptions = [f"{m.name} (local, {m.size_gb:.1f} GB)" for m in infos]
    if api is not None:
        for m in cfg.api.models:
            names.append(m.name)
            costs[m.name] = api_call_cost(m, cfg.api.credits_per_usd)
            descriptions.append(f"{m.name} (API, ${m.output_usd_per_mtok:g} per 1M output tokens)")
    if not names:
        raise ConfigError("no models to use: enable ollama and/or api")
    return ModelPool(ModelRouter(local if infos else None, api), names, costs, api, descriptions)


def run_llm_experiment(
    cfg: Config,
    out_dir: str | Path | None = None,
    progress: Progress | None = None,
    client: Any | None = None,
    api: APIClient | None = None,
) -> dict:
    """The same experiment with real models (local and/or paid API) on auto-checkable tasks."""
    from .results import summarize, write_results

    sandbox = Sandbox(cfg.sandbox)
    pool = build_model_pool(cfg, sandbox, client, api)
    cfg.models = [ModelSpec(name) for name in pool.names]
    models = pool.names
    if cfg.baseline.model not in models:
        cfg.baseline.model = models[0]
    cfg.validate()
    if progress is not None:
        progress("models: " + "; ".join(pool.descriptions))
        if pool.api is not None:
            progress(f"paid API spending cap: ${cfg.sandbox.max_api_spend_usd:g}")

    solver = LLMSolver(pool.client, cfg.ollama, sandbox, pool.costs, cfg.api.credits_per_usd)
    results = []
    for offset in range(cfg.experiment.seeds):
        seed = cfg.experiment.base_seed + offset
        probe = _verifiable_market(cfg, seed)
        start = _seed_genomes(cfg, seed, probe.categories, models, probe.demand)
        for arm in cfg.experiment.arms:
            if progress is not None:
                progress(f"seed {seed}, arm {arm}")
            market = _verifiable_market(cfg, seed)
            if ARMS[arm][0] == "menu":
                results.append(run_router_arm(cfg, seed, market, solver, models, log_attempts=True, progress=progress))
            else:
                results.append(
                    run_arm(
                        cfg, arm, seed, start[ARMS[arm][0]], market, solver, models,
                        log_attempts=True, progress=progress,
                    )
                )
            if progress is not None and pool.api is not None:
                progress(f"  API so far: {pool.api.calls} calls, ${pool.api.spent_usd:.4f}")
    summary = summarize(results, cfg)
    if pool.api is not None:
        summary["api"] = {"calls": pool.api.calls, "spent_usd": pool.api.spent_usd}
    if out_dir is not None:
        write_results(Path(out_dir), cfg, results, summary)
    return summary
