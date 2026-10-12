"""Command line interface: ``astra <command>``."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .api_client import APIClient, APIError
from .config import Config, ConfigError, load_config
from .experiment import build_model_pool, run_experiment, run_llm_experiment
from .ollama_client import OllamaClient, OllamaError, discover_models
from .owner import Workspace, WorkspaceError
from .results import format_summary
from .sandbox import Sandbox, SandboxViolation
from .solvers import LLMSolver


def _load(args: argparse.Namespace, default: str | None = None) -> Config:
    overrides = list(args.set or [])
    if getattr(args, "generations", None):
        overrides.append(f"experiment.generations={args.generations}")
    if getattr(args, "seeds", None):
        overrides.append(f"experiment.seeds={args.seeds}")
    path = args.config or default
    if path is not None and not Path(path).exists():
        raise ConfigError(f"config file {path} not found (run from the repository root or pass --config)")
    return load_config(path, overrides)


def _out_dir(args: argparse.Namespace, cfg: Config) -> Path:
    if args.out:
        return Path(args.out)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path(cfg.experiment.results_dir) / f"{cfg.experiment.name}-{stamp}"


def cmd_run(args: argparse.Namespace) -> int:
    cfg = _load(args)
    out = _out_dir(args, cfg)
    print(
        f"Running '{cfg.experiment.name}': {cfg.experiment.seeds} seed(s) x {cfg.experiment.generations} "
        f"generations, arms: {', '.join(cfg.experiment.arms)}"
    )
    summary = run_experiment(cfg, out, progress=None if args.quiet else print)
    print()
    print(format_summary(summary))
    print(f"\nFull report: {out / 'report.md'}")
    return 0


def cmd_ollama_run(args: argparse.Namespace) -> int:
    cfg = _load(args, default="config/ollama.yaml")
    out = _out_dir(args, cfg)
    print(f"Running '{cfg.experiment.name}' with real models", flush=True)
    summary = run_llm_experiment(cfg, out, progress=lambda line: print(line, flush=True))
    print()
    print(format_summary(summary))
    print(f"\nFull report: {out / 'report.md'}  (every model answer: {out / 'attempts.jsonl'})")
    return 0


def _client(cfg: Config) -> OllamaClient:
    return OllamaClient(cfg.ollama.host, Sandbox(cfg.sandbox), cfg.sandbox.request_timeout)


def cmd_check(args: argparse.Namespace) -> int:
    cfg = _load(args, default="config/ollama.yaml")
    question = "What is 2 + 2? Reply in the form 'ANSWER: <number>'."
    if cfg.ollama.enabled:
        client = _client(cfg)
        print(f"Ollama {client.version()} at {cfg.ollama.host}")
        usable = discover_models(client, cfg.ollama.models, cfg.ollama.max_model_size_gb)
        names = {m.name for m in usable}
        for m in client.list_models():
            mark = "use " if m.name in names else "skip"
            print(f"  [{mark}] {m.name:<50} {m.size_gb:6.1f} GB  {m.parameter_size}")
        result = client.generate(usable[0].name, question, num_predict=32, think=cfg.ollama.think)
        print(f"Test generation with {usable[0].name}: {result.text!r} in {result.seconds:.2f} s")
    if cfg.api.enabled:
        api = APIClient(cfg.api, Sandbox(cfg.sandbox))
        print(f"API {cfg.api.base_url}, spending cap ${cfg.sandbox.max_api_spend_usd:g}")
        for m in cfg.api.models:
            result = api.generate(m.name, question, num_predict=16, effort=0.5)
            print(f"  {m.name}: {result.text!r} in {result.seconds:.2f} s for ${result.cost_usd:.6f}")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    cfg = _load(args, default="config/owner.yaml")
    models = build_model_pool(cfg, Sandbox(cfg.sandbox)).names
    categories = [c.name for c in cfg.market.categories]
    ws = Workspace.create(args.workspace, cfg, models, categories, seed=args.seed)
    print(f"Created workspace {ws.root} with {len(ws.population.alive())} agents using {models}")
    print(f"Next: astra add-tasks --workspace {ws.root} tasks/example_tasks.yaml")
    return 0


def cmd_add_tasks(args: argparse.Namespace) -> int:
    ws = Workspace.open(args.workspace)
    added = ws.add_tasks(args.file)
    print(f"Added {len(added)} task(s): {', '.join(t.id for t in added)}")
    return 0


def cmd_work(args: argparse.Namespace) -> int:
    ws = Workspace.open(args.workspace)
    pool = build_model_pool(ws.cfg, ws.sandbox)
    solver = LLMSolver(pool.client, ws.cfg.ollama, ws.sandbox, pool.costs, ws.cfg.api.credits_per_usd)
    done = ws.work(solver, limit=args.limit, progress=print)
    for t in done:
        check = "" if t.auto_check is None else f", automatic check {'passed' if t.auto_check else 'FAILED'}"
        print(f"{t.id}: {t.status}, cost {t.cost:.3f}{check} -> {ws.root / t.output_file}")
    if not done:
        print("No open tasks.")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    ws = Workspace.open(args.workspace)
    if args.task:
        if args.accept == args.reject:
            raise WorkspaceError("pass exactly one of --accept or --reject")
        t = ws.review(args.task, accepted=args.accept, paid=args.paid, note=args.note or "", reopen=args.reopen)
        print(f"{t.id}: {t.status}" + (f", paid {t.paid:g}" if t.paid is not None else ""))
        return 0
    pending = ws.tasks_with_status("in_review")
    if not pending:
        print("Nothing to review.")
        return 0
    for t in pending:
        print(f"\n{t.id} [{t.category}] price {t.price:g}, agent {t.agent_id}, cost {t.cost:.3f}")
        print(f"  result: {ws.root / t.output_file}")
        if t.auto_check:
            print("  automatic check passed")
        answer = input("  [a]ccept / [r]eject / [s]kip / [q]uit: ").strip().lower()
        if answer.startswith("q"):
            break
        if answer.startswith("a"):
            raw = input(f"  amount the client paid [{t.price:g}]: ").strip()
            ws.review(t.id, accepted=True, paid=float(raw) if raw else None)
        elif answer.startswith("r"):
            reopen = input("  give the task to another agent? [y/N]: ").strip().lower().startswith("y")
            ws.review(t.id, accepted=False, reopen=reopen)
    return 0


def cmd_evolve(args: argparse.Namespace) -> int:
    ws = Workspace.open(args.workspace)
    waiting = ws.tasks_with_status("in_review")
    if waiting and not args.force:
        raise WorkspaceError(
            f"{len(waiting)} task(s) still in review; review them first or pass --force"
        )
    events = ws.close_generation()
    print(
        f"Generation {ws.generation - 1} closed: {len(events.births)} born, "
        f"{len(events.bankrupt)} bankrupt, {len(events.defunded)} defunded, "
        f"{len(events.outcompeted)} outcompeted"
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    print(Workspace.open(args.workspace).status_text())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="astra", description="Astra Evolution: an evolving population of economic AI agents."
    )
    parser.add_argument("--version", action="version", version=f"astra-evolution {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def config_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("-c", "--config", help="YAML config file (values override the defaults)")
        p.add_argument(
            "--set", action="append", metavar="KEY=VALUE",
            help="override a config value, e.g. --set evolution.mutation_rate=0.5 (repeatable)",
        )

    def experiment_args(p: argparse.ArgumentParser) -> None:
        config_args(p)
        p.add_argument("--generations", type=int, help="number of generations")
        p.add_argument("--seeds", type=int, help="number of independent repetitions")
        p.add_argument("--out", help="output directory (default: results/<name>-<timestamp>)")

    p = sub.add_parser("run", help="simulated experiment: evolution vs. static control arms")
    experiment_args(p)
    p.add_argument("--quiet", action="store_true", help="only print the final summary")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser(
        "ollama-run", aliases=["llm-run"],
        help="experiment with real models (local Ollama and/or a paid API) on auto-checked tasks",
    )
    experiment_args(p)
    p.set_defaults(func=cmd_ollama_run)

    p = sub.add_parser("ollama-check", aliases=["check"], help="check model connections and list usable models")
    config_args(p)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("init", help="owner mode: create a workspace with a fresh population")
    config_args(p)
    p.add_argument("--workspace", required=True)
    p.add_argument("--seed", type=int, default=1)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("add-tasks", help="owner mode: add real tasks from a YAML file")
    p.add_argument("--workspace", required=True)
    p.add_argument("file")
    p.set_defaults(func=cmd_add_tasks)

    p = sub.add_parser("work", help="owner mode: let agents draft results for open tasks")
    p.add_argument("--workspace", required=True)
    p.add_argument("--limit", type=int, help="at most this many tasks")
    p.set_defaults(func=cmd_work)

    p = sub.add_parser("review", help="owner mode: accept or reject drafted results")
    p.add_argument("--workspace", required=True)
    p.add_argument("task", nargs="?", help="task id (omit for interactive review)")
    p.add_argument("--accept", action="store_true")
    p.add_argument("--reject", action="store_true")
    p.add_argument("--paid", type=float, help="amount the client actually paid (default: task price)")
    p.add_argument("--note")
    p.add_argument("--reopen", action="store_true", help="after rejecting, offer the task again")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("evolve", help="owner mode: close the generation and run selection")
    p.add_argument("--workspace", required=True)
    p.add_argument("--force", action="store_true", help="evolve even with tasks still in review")
    p.set_defaults(func=cmd_evolve)

    p = sub.add_parser("status", help="owner mode: population, money and tasks")
    p.add_argument("--workspace", required=True)
    p.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, SandboxViolation, OllamaError, APIError, WorkspaceError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
