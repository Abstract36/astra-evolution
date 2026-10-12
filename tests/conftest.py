from __future__ import annotations

import re
from typing import Callable

import pytest

from astra.config import Config
from astra.ollama_client import GenerateResult, ModelInfo


class FakeLLM:
    """Stands in for OllamaClient: answers with ``reply(model, prompt)``."""

    def __init__(self, reply: Callable[[str, str], str] | None = None, seconds: float = 1.0):
        self.reply = reply or (lambda model, prompt: "ANSWER: 42")
        self.seconds = seconds
        self.calls: list[tuple[str, str, int]] = []

    def generate(self, model, prompt, *, temperature=0.2, num_predict=256, think=False, effort=1.0):
        self.calls.append((model, prompt, num_predict))
        return GenerateResult(self.reply(model, prompt), self.seconds, 10, 20, model)

    def list_models(self):
        return [
            ModelInfo("tiny:1b", 1.0, "1B", ["completion"]),
            ModelInfo("mid:7b", 4.5, "7B", ["completion"]),
            ModelInfo("embed:1b", 0.5, "1B", ["embedding"]),
        ]


def solve_arithmetic(model: str, prompt: str) -> str:
    """A fake model that gets arithmetic right and everything else wrong."""
    m = re.search(r"Compute (\d+) \* (\d+) ([+-]) (\d+)", prompt)
    if not m:
        return "ANSWER: nope"
    a, b, op, c = int(m[1]), int(m[2]), m[3], int(m[4])
    return f"ANSWER: {a * b + c if op == '+' else a * b - c}"


@pytest.fixture
def small_cfg() -> Config:
    """A fast configuration for tests."""
    cfg = Config()
    cfg.experiment.generations = 8
    cfg.experiment.seeds = 2
    cfg.experiment.population_size = 10
    cfg.market.tasks_per_generation = 40
    return cfg.validate()
