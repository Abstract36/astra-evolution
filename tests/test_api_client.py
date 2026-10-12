import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from astra.api_client import APIClient, APIError, ModelRouter
from astra.config import APIConfig, APIModelSpec, Config, SandboxConfig
from astra.experiment import run_llm_experiment
from astra.sandbox import Sandbox, SandboxViolation
from tests.conftest import FakeLLM, solve_arithmetic


class FakeChatAPI(BaseHTTPRequestHandler):
    requests: list = []
    fail_next: list = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeChatAPI.requests.append((self.headers.get("Authorization"), payload))
        if FakeChatAPI.fail_next:
            code = FakeChatAPI.fail_next.pop(0)
            self.send_response(code)
            self.end_headers()
            self.wfile.write(b'{"error": "busy"}')
            return
        body = json.dumps(
            {
                "choices": [{"message": {"content": "ANSWER: 4", "reasoning_content": "2+2"}}],
                "usage": {
                    "prompt_tokens": 1000,
                    "prompt_cache_hit_tokens": 400,
                    "prompt_cache_miss_tokens": 600,
                    "completion_tokens": 2000,
                },
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def server():
    httpd = HTTPServer(("127.0.0.1", 0), FakeChatAPI)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def make_client(server, cap=1.0):
    cfg = APIConfig(enabled=True, base_url=server, models=[APIModelSpec("flash", 0.3, 0.006, 1.2)])
    return APIClient(cfg, Sandbox(SandboxConfig(max_api_spend_usd=cap)), api_key="test-key")


def test_cost_is_computed_from_reported_usage(server):
    client = make_client(server)
    result = client.generate("flash", "2+2?", num_predict=50, effort=0.5)
    expected = (400 * 0.006 + 600 * 0.3 + 2000 * 1.2) / 1e6
    assert result.text == "ANSWER: 4"
    assert result.cost_usd == pytest.approx(expected)
    assert client.spent_usd == pytest.approx(expected) and client.calls == 1
    auth, payload = FakeChatAPI.requests[-1]
    assert auth == "Bearer test-key"
    assert payload["thinking"] == {"type": "disabled"} and payload["max_tokens"] == 50


@pytest.mark.parametrize("effort, level", [(1.0, "low"), (1.9, "high")])
def test_effort_turns_thinking_on(server, effort, level):
    make_client(server).generate("flash", "2+2?", num_predict=50, effort=effort)
    _, payload = FakeChatAPI.requests[-1]
    assert payload["thinking"] == {"type": "enabled"} and payload["reasoning_effort"] == level
    assert payload["max_tokens"] == 50 + 1024


def test_spending_cap_refuses_calls_in_advance(server):
    client = make_client(server, cap=0.0026)
    client.generate("flash", "2+2?", num_predict=50, effort=0.5)  # costs $0.00258
    calls_before = len(FakeChatAPI.requests)
    with pytest.raises(SandboxViolation, match="spending cap"):
        client.generate("flash", "2+2?", num_predict=50, effort=0.5)
    assert len(FakeChatAPI.requests) == calls_before  # nothing was sent


def test_transient_errors_are_retried(server, monkeypatch):
    monkeypatch.setattr("astra.api_client.time.sleep", lambda s: None)
    FakeChatAPI.fail_next[:] = [503]
    assert make_client(server).generate("flash", "hi", effort=0.5).text == "ANSWER: 4"
    FakeChatAPI.fail_next[:] = [401]
    with pytest.raises(APIError, match="401"):
        make_client(server).generate("flash", "hi", effort=0.5)


def test_key_and_host_are_required(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(APIError, match="DEEPSEEK_API_KEY"):
        APIClient(APIConfig(enabled=True), Sandbox(SandboxConfig(allowed_hosts=["api.deepseek.com"])))
    with pytest.raises(SandboxViolation):  # not in allowed_hosts by default
        APIClient(APIConfig(enabled=True), Sandbox(SandboxConfig()), api_key="k")


def test_router_sends_models_to_their_backend(server):
    api = make_client(server)
    local = FakeLLM(lambda m, p: "local")
    router = ModelRouter(local, api)
    assert router.generate("flash", "x", effort=0.5).cost_usd is not None
    assert router.generate("tiny:1b", "x").text == "local"
    with pytest.raises(APIError):
        ModelRouter(None, api).generate("tiny:1b", "x")


def test_mixed_local_and_api_experiment(server, tmp_path):
    cfg = Config()
    cfg.experiment.generations = 2
    cfg.experiment.seeds = 1
    cfg.experiment.population_size = 6
    cfg.experiment.arms = ["evolving"]
    cfg.market.tasks_per_generation = 8
    cfg.market.external_competition = False
    cfg.sandbox.max_api_spend_usd = 5.0
    cfg.api.enabled = True
    cfg.api.models = [APIModelSpec("flash", 0.3, 0.006, 1.2)]
    api = make_client(server, cap=5.0)
    summary = run_llm_experiment(cfg.validate(), tmp_path, client=FakeLLM(solve_arithmetic), api=api)
    attempts = [json.loads(line) for line in (tmp_path / "attempts.jsonl").read_text().splitlines()]
    api_attempts = [a for a in attempts if a["model"] == "flash"]
    assert summary["api"]["calls"] == api.calls
    if api_attempts:  # API attempts are billed by tokens: $0.0026 x 1000 credits per call
        assert all(a["cost"] >= 2.5 for a in api_attempts)
    assert "Paid API" in (tmp_path / "report.md").read_text()
