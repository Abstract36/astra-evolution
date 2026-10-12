from pathlib import Path

import pytest
import yaml

from astra.cli import main
from astra.config import load_config
from astra.owner import Workspace, WorkspaceError
from astra.sandbox import Sandbox
from astra.solvers import LLMSolver
from tests.conftest import FakeLLM

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def workspace(tmp_path):
    cfg = load_config(ROOT / "config" / "owner.yaml")
    ws = Workspace.create(tmp_path / "node", cfg, ["tiny:1b"], [c.name for c in cfg.market.categories], seed=3)
    ws.add_tasks(ROOT / "tasks" / "example_tasks.yaml")
    return ws


def solver_for(ws, reply):
    return LLMSolver(FakeLLM(reply), ws.cfg.ollama, Sandbox(ws.cfg.sandbox), {"tiny:1b": 1.0})


def test_full_owner_cycle(workspace):
    reply = lambda model, prompt: "anna.k@poczta.pl\ndef slugify(text): ..."  # noqa: E731
    done = workspace.work(solver_for(workspace, reply))
    assert len(done) == 4
    assert all((workspace.root / t.output_file).exists() for t in done)
    assert {t.status for t in done} == {"in_review"}

    reopened = Workspace.open(workspace.root)  # state survives a restart
    reopened.review("coffee-landing-01", accepted=True, paid=35)
    reopened.review("market-scan-01", accepted=False, reopen=True)
    assert reopened.tasks["coffee-landing-01"].paid == 35
    assert reopened.tasks["market-scan-01-r1"].status == "open"
    agent = reopened.population.get(reopened.tasks["coffee-landing-01"].agent_id)
    assert agent.lifetime_revenue >= 35

    events = reopened.close_generation()
    assert reopened.generation == 1 and not events.bankrupt
    assert "generation 1" in reopened.status_text()
    ledger = (workspace.root / "ledger.jsonl").read_text().splitlines()
    assert any('"revenue"' in line for line in ledger)


def test_failed_automatic_check_rejects_without_asking(workspace):
    done = workspace.work(solver_for(workspace, lambda m, p: "I cannot help with that."))
    statuses = {t.id: t.status for t in done}
    assert statuses["csv-cleanup-01"] == "rejected"
    assert statuses["python-slugify-01"] == "rejected"
    assert statuses["coffee-landing-01"] == "in_review"  # manual tasks wait for the owner


def test_task_validation(workspace, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump({"tasks": [{"id": "x y", "category": "a", "prompt": "p", "price": 1}]}))
    with pytest.raises(WorkspaceError, match="task id"):
        workspace.add_tasks(bad)
    with pytest.raises(WorkspaceError, match="already exists"):
        workspace.add_tasks(ROOT / "tasks" / "example_tasks.yaml")
    with pytest.raises(WorkspaceError, match="not in_review"):
        workspace.review("coffee-landing-01", accepted=True)


def test_new_categories_extend_every_agent(workspace, tmp_path):
    extra = tmp_path / "extra.yaml"
    extra.write_text(yaml.safe_dump({"tasks": [{"id": "logo-1", "category": "design", "prompt": "p", "price": 5}]}))
    workspace.add_tasks(extra)
    assert all("design" in a.genome.focus for a in workspace.population.alive())


def test_workspace_cannot_be_created_twice(workspace):
    with pytest.raises(WorkspaceError, match="already contains"):
        Workspace.create(workspace.root, workspace.cfg, ["tiny:1b"], ["a"])


def test_cli_reports_missing_workspace(tmp_path, capsys):
    assert main(["status", "--workspace", str(tmp_path / "nothing")]) == 2
    assert "no workspace" in capsys.readouterr().err
