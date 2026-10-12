import json
import random

import pytest

from astra.config import ARMS
from astra.experiment import run_arm, run_experiment, tuned_genomes
from astra.market import SimulatedMarket
from astra.solvers import SimulatedSolver


def test_experiment_writes_all_outputs(small_cfg, tmp_path):
    summary = run_experiment(small_cfg, tmp_path)
    for name in ("config.yaml", "generations.csv", "agents.jsonl", "summary.json", "report.md", "capital.svg"):
        assert (tmp_path / name).exists(), name
    assert set(summary["arms"]) == set(ARMS)
    assert len(summary["per_run"]) == len(ARMS) * small_cfg.experiment.seeds
    assert json.loads((tmp_path / "summary.json").read_text())["generations"] == small_cfg.experiment.generations
    report = (tmp_path / "report.md").read_text()
    assert "## Verdict" in report and "capital.svg" in report
    assert (tmp_path / "capital.svg").read_text().startswith("<svg")


def test_experiment_is_deterministic(small_cfg):
    assert run_experiment(small_cfg)["per_run"] == run_experiment(small_cfg)["per_run"]


@pytest.mark.parametrize("arm", list(ARMS))
def test_money_is_conserved(small_cfg, arm):
    """wealth = allocated + revenue - compute - sales - upkeep - spawn fees, every generation."""
    small_cfg.experiment.save_ledger = True
    models = [m.name for m in small_cfg.models]
    market = SimulatedMarket(small_cfg.market, random.Random(1))
    genomes = tuned_genomes(small_cfg.baseline, market.demand, small_cfg.experiment.population_size)
    solver = SimulatedSolver(small_cfg.models, small_cfg.economy)
    result = run_arm(small_cfg, arm, 1, genomes, market, solver, models)
    expected = result.initial_capital
    for row in result.rows:
        expected += row["revenue"] - row["compute_cost"] - row["sales_cost"] - row["upkeep"] - row["spawn_fees"]
        assert row["wealth"] == pytest.approx(expected)
    # The ledger explains every agent balance.
    for agent in result.agents:
        posted = sum(t["amount"] for t in result.ledger if t["agent_id"] == agent["id"])
        assert posted == pytest.approx(agent["balance"], abs=1e-3)  # records round to 4 decimals


def test_population_never_exceeds_sandbox(small_cfg):
    small_cfg.sandbox.max_population = 12
    summary = run_experiment(small_cfg)
    assert max(r["final_agents"] for r in summary["per_run"]) <= 12
    for arm in summary["by_generation"].values():
        assert max(g["population"] for g in arm) <= 12


def test_tuned_genomes_split_specialists_by_demand(small_cfg):
    genomes = tuned_genomes(small_cfg.baseline, {"a": 0.5, "b": 0.3, "c": 0.2}, 10)
    specialties = [g.specialty for g in genomes]
    assert (specialties.count("a"), specialties.count("b"), specialties.count("c")) == (5, 3, 2)
