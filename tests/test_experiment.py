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
    assert list(summary["arms"]) == small_cfg.experiment.arms
    assert len(summary["per_run"]) == len(small_cfg.experiment.arms) * small_cfg.experiment.seeds
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


def test_verdicts_separate_wins_losses_and_ties():
    from astra.results import _judge

    def comparison(diff, wins, seeds):
        return {"capital_multiple_diff": {"mean": diff}, "wins": wins, "seeds": seeds}

    assert _judge([comparison(1.2, 9, 10)]) == "Yes: "
    assert _judge([comparison(-4.7, 0, 10)]) == "No: "
    assert _judge([comparison(0.004, 1, 1)]).startswith("No clear difference (one seed")
    assert _judge([comparison(1.2, 9, 10), comparison(-0.5, 3, 10)]).startswith("Not consistently")


def test_separate_seeds_merge_into_the_same_summary(small_cfg, tmp_path):
    from astra.results import merge_results

    together = run_experiment(small_cfg)
    small_cfg.experiment.seeds = 1
    run_experiment(small_cfg, tmp_path / "a")
    small_cfg.experiment.base_seed = 2
    run_experiment(small_cfg, tmp_path / "b")
    merged = merge_results([tmp_path / "a", tmp_path / "b"], tmp_path / "merged")
    assert len(merged["per_run"]) == len(together["per_run"])
    for got, want in zip(merged["per_run"], together["per_run"]):  # CSV keeps 6 decimals
        assert got.keys() == want.keys()
        for key, value in want.items():
            assert got[key] == (pytest.approx(value, abs=1e-4) if isinstance(value, float) else value), key
    assert (tmp_path / "merged" / "report.md").exists()
    with pytest.raises(ValueError, match="more than one"):
        merge_results([tmp_path / "a", tmp_path / "a"], tmp_path / "bad")
