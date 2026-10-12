import json
import random
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from astra.agent import Agent, Genome
from astra.config import Config, OllamaConfig, SandboxConfig
from astra.experiment import run_llm_experiment
from astra.market import Task
from astra.ollama_client import OllamaClient, OllamaError, discover_models, strip_thinking
from astra.sandbox import Sandbox
from astra.solvers import LLMSolver
from tests.conftest import FakeLLM, solve_arithmetic


class FakeOllama(BaseHTTPRequestHandler):
    requests: list = []

    def log_message(self, *args):
        pass

    def _send(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/version":
            self._send({"version": "0.0-test"})
        elif self.path == "/api/tags":
            self._send({"models": [{"name": "tiny:1b", "size": 2_000_000_000, "details": {"parameter_size": "1B"}}]})
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.requests.append(payload)
        if payload["model"] == "missing":
            self._send({"error": "model 'missing' not found"}, 404)
            return
        self._send(
            {
                "response": "<think>hmm</think>ANSWER: 4",
                "total_duration": 3_000_000_000,
                "load_duration": 1_000_000_000,
                "prompt_eval_count": 12,
                "eval_count": 5,
            }
        )


@pytest.fixture(scope="module")
def server():
    httpd = HTTPServer(("127.0.0.1", 0), FakeOllama)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_client_talks_to_ollama_api(server):
    client = OllamaClient(server, Sandbox(SandboxConfig()))
    assert client.version() == "0.0-test"
    [model] = client.list_models()
    assert model.name == "tiny:1b" and model.size_gb == pytest.approx(2.0)
    result = client.generate("tiny:1b", "2+2?", num_predict=7, think=False)
    assert result.text == "ANSWER: 4"
    assert result.seconds == pytest.approx(2.0)  # model loading is not billed
    sent = FakeOllama.requests[-1]
    assert sent["options"]["num_predict"] == 7 and sent["think"] is False and sent["stream"] is False


def test_client_reports_http_errors(server):
    client = OllamaClient(server, Sandbox(SandboxConfig()))
    with pytest.raises(OllamaError, match="not found"):
        client.generate("missing", "hi")


def test_unreachable_server_gives_a_helpful_error():
    client = OllamaClient("http://127.0.0.1:9", Sandbox(SandboxConfig()), timeout=2)
    with pytest.raises(OllamaError, match="ollama serve"):
        client.version()


def test_strip_thinking():
    assert strip_thinking("<think>a\nb</think>\n ok") == "ok"
    assert strip_thinking("reasoning cut off</think>answer") == "answer"


def test_discover_models_filters_and_sorts():
    client = FakeLLM()
    assert [m.name for m in discover_models(client, [], 10)] == ["tiny:1b", "mid:7b"]
    assert [m.name for m in discover_models(client, [], 2)] == ["tiny:1b"]
    with pytest.raises(OllamaError, match="not installed"):
        discover_models(client, ["ghost:3b"], 10)


def make_solver(reply, review=False, effort=1.0):
    client = FakeLLM(reply, seconds=2.0)
    solver = LLMSolver(client, OllamaConfig(cost_per_second=0.5), Sandbox(SandboxConfig()), {"tiny:1b": 0.8})
    agent = Agent(1, Genome({"arithmetic": 1.0}, "tiny:1b", effort=effort, review=review))
    return client, solver, agent


def arithmetic_task():
    return Task("t", 0, "arithmetic", 0.5, 1.0, 4.0, payload={"prompt": "Compute 12 * 3 + 4.", "answer": 40, "kind": "int"})


def test_llm_solver_checks_answers_and_bills_time():
    client, solver, agent = make_solver(solve_arithmetic)
    outcome = solver.attempt(agent, arithmetic_task(), random.Random(0))
    assert outcome.success and outcome.cost == pytest.approx(1.0)
    assert "step by step" in client.calls[0][1]


def test_review_pass_doubles_the_calls():
    client, solver, agent = make_solver(lambda m, p: "ANSWER: 41", review=True, effort=0.6)
    outcome = solver.attempt(agent, arithmetic_task(), random.Random(0))
    assert not outcome.success and len(client.calls) == 2 and outcome.seconds == pytest.approx(4.0)
    assert "Reply with only the final answer" in client.calls[0][1]


def test_cost_estimate_uses_memory_once_available():
    _, solver, agent = make_solver(solve_arithmetic)
    prior = solver.estimate_cost(agent, arithmetic_task())
    agent.memory.record("arithmetic", True, 9.0)
    assert prior != 9.0 and solver.estimate_cost(agent, arithmetic_task()) == 9.0


def test_llm_experiment_end_to_end(tmp_path):
    cfg = Config()
    cfg.experiment.generations = 3
    cfg.experiment.seeds = 1
    cfg.experiment.population_size = 4
    cfg.experiment.arms = ["evolving", "static_random"]
    cfg.market.tasks_per_generation = 6
    cfg.market.external_competition = False
    summary = run_llm_experiment(cfg.validate(), tmp_path, client=FakeLLM(solve_arithmetic, seconds=0.5))
    assert set(summary["arms"]) == {"evolving", "static_random"}
    attempts = [json.loads(line) for line in (tmp_path / "attempts.jsonl").read_text().splitlines()]
    assert attempts and all(a["model"] in ("tiny:1b", "mid:7b") for a in attempts)
    assert any(a["success"] for a in attempts if a["category"] == "arithmetic")
    assert not any(a["success"] for a in attempts if a["category"] != "arithmetic")
