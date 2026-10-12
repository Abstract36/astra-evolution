import pytest

from astra.config import SandboxConfig
from astra.ollama_client import OllamaClient
from astra.sandbox import Sandbox, SandboxViolation


@pytest.fixture
def sandbox():
    return Sandbox(SandboxConfig(max_population=3, max_spawns_per_generation=1, max_tokens_per_call=100))


@pytest.mark.parametrize("url", ["http://127.0.0.1:11434", "http://localhost:11434/api", "http://[::1]:11434"])
def test_local_hosts_are_allowed(sandbox, url):
    sandbox.check_url(url)


@pytest.mark.parametrize("url", ["http://example.com", "https://10.0.0.5:11434", "file:///etc/passwd", "ftp://localhost"])
def test_other_hosts_are_blocked(sandbox, url):
    with pytest.raises(SandboxViolation):
        sandbox.check_url(url)


def test_ollama_client_refuses_remote_hosts(sandbox):
    with pytest.raises(SandboxViolation):
        OllamaClient("http://203.0.113.7:11434", sandbox)


def test_population_and_spawn_limits(sandbox):
    sandbox.check_population(2)
    with pytest.raises(SandboxViolation):
        sandbox.check_population(3)
    sandbox.check_spawn(0)
    with pytest.raises(SandboxViolation):
        sandbox.check_spawn(1)


def test_token_clamp(sandbox):
    assert sandbox.clamp_tokens(5000) == 100
    assert sandbox.clamp_tokens(0) == 1
