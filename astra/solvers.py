"""Solvers turn (agent, task) into an outcome with a cost.

``SimulatedSolver`` uses a transparent model of quality and cost so that large
experiments run in seconds. ``LLMSolver`` runs the agent's real model through
Ollama and measures the compute time it actually used.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Protocol

from .agent import Agent
from .config import EconomyConfig, ModelSpec, OllamaConfig
from .market import Task
from .ollama_client import GenerateResult
from .sandbox import Sandbox
from .verifiable import check_answer


@dataclass
class Outcome:
    success: bool
    cost: float
    output: str = ""
    seconds: float = 0.0


class Solver(Protocol):
    def estimate_cost(self, agent: Agent, task: Task) -> float: ...

    def attempt(self, agent: Agent, task: Task, rng: random.Random) -> Outcome: ...


class SimulatedSolver:
    """Success depends on model quality, specialization, effort and review.

    capability = quality * (0.35 + 0.65 * sqrt(focus)) + 0.12 * ln(effort) + review bonus
    P(success) = sigmoid(sharpness * (capability - difficulty))
    cost       = size * model cost * effort * (1 + review overhead)
    """

    REVIEW_BONUS = 0.06

    def __init__(self, models: list[ModelSpec], economy: EconomyConfig):
        self.models = {m.name: m for m in models}
        self.econ = economy

    def capability(self, agent: Agent, task: Task) -> float:
        g = agent.genome
        focus = g.focus.get(task.category, 0.0)
        value = self.models[g.model].quality * (0.35 + 0.65 * math.sqrt(focus))
        value += 0.12 * math.log(g.effort)
        if g.review:
            value += self.REVIEW_BONUS
        return value

    def success_probability(self, agent: Agent, task: Task) -> float:
        x = self.econ.success_sharpness * (self.capability(agent, task) - task.difficulty)
        return 1.0 / (1.0 + math.exp(-x))

    def estimate_cost(self, agent: Agent, task: Task) -> float:
        g = agent.genome
        cost = task.size * self.models[g.model].cost_per_unit * g.effort
        if g.review:
            cost *= 1.0 + self.econ.review_cost_overhead
        return cost

    def attempt(self, agent: Agent, task: Task, rng: random.Random) -> Outcome:
        p = self.success_probability(agent, task)
        cost = self.estimate_cost(agent, task) * max(0.0, rng.gauss(1.0, self.econ.cost_noise))
        return Outcome(success=rng.random() < p, cost=cost)


class TextModel(Protocol):
    def generate(
        self, model: str, prompt: str, *, temperature: float, num_predict: int, think: bool | None
    ) -> GenerateResult: ...


VERIFIABLE_DIRECT = (
    "Solve the task. Reply with only the final answer on one line, in the form 'ANSWER: <answer>'."
)
VERIFIABLE_STEPWISE = (
    "Solve the task. Think step by step briefly, then give the final answer on the last line, "
    "in the form 'ANSWER: <answer>'."
)
VERIFIABLE_REVIEW = (
    "Below is a task and a proposed solution. Check the solution carefully; if it is wrong, "
    "solve the task again. Finish with the final answer on the last line, in the form "
    "'ANSWER: <answer>'.\n\nTask:\n{task}\n\nProposed solution:\n{draft}"
)
OWNER_TASK = (
    "You are an expert in {category}. Complete the client's task below and deliver a finished, "
    "ready-to-use result, written in the language of the task.{plan}\n\n"
    "Task: {title}\n\n{prompt}"
)
OWNER_REVIEW = (
    "Improve the draft below: fix errors, fill gaps and make it ready to deliver to the client. "
    "Return only the improved result.\n\nTask: {title}\n\n{prompt}\n\nDraft:\n{draft}"
)


class LLMSolver:
    """Runs the agent's own model; cost = measured compute seconds * cost_per_second."""

    def __init__(self, client: TextModel, cfg: OllamaConfig, sandbox: Sandbox, model_sizes: dict[str, float]):
        self.client = client
        self.cfg = cfg
        self.sandbox = sandbox
        self.model_sizes = model_sizes

    def estimate_cost(self, agent: Agent, task: Task) -> float:
        known = agent.memory.mean_cost(task.category)
        if known is not None:
            return known
        g = agent.genome
        seconds = (1.0 + 0.6 * self.model_sizes.get(g.model, 5.0)) * g.effort
        if g.review:
            seconds *= 2
        return seconds * self.cfg.cost_per_second

    def _generate(self, agent: Agent, prompt: str, tokens: int) -> GenerateResult:
        return self.client.generate(
            agent.genome.model,
            prompt,
            temperature=self.cfg.temperature,
            num_predict=self.sandbox.clamp_tokens(int(tokens * agent.genome.effort)),
            think=self.cfg.think,
        )

    def attempt(self, agent: Agent, task: Task, rng: random.Random) -> Outcome:
        """Solve an auto-checkable task (see ``verifiable.py``)."""
        style = VERIFIABLE_STEPWISE if agent.genome.effort >= 1.0 else VERIFIABLE_DIRECT
        question = task.payload["prompt"]
        first = self._generate(agent, f"{style}\n\nTask: {question}", self.cfg.base_tokens)
        text, seconds = first.text, first.seconds
        if agent.genome.review:
            second = self._generate(
                agent, VERIFIABLE_REVIEW.format(task=question, draft=text), self.cfg.base_tokens
            )
            text, seconds = second.text, seconds + second.seconds
        success = check_answer(task.payload["kind"], task.payload["answer"], text)
        return Outcome(success, seconds * self.cfg.cost_per_second, text, seconds)

    def produce(self, agent: Agent, task: Task) -> Outcome:
        """Draft a free-form deliverable for an owner task; the owner judges it."""
        fields = {
            "category": task.category.replace("_", " "),
            "title": task.payload.get("title") or task.id,
            "prompt": task.payload["prompt"],
        }
        plan = " Plan the structure briefly before writing." if agent.genome.effort >= 1.0 else ""
        first = self._generate(agent, OWNER_TASK.format(plan=plan, **fields), self.cfg.owner_tokens)
        text, seconds = first.text, first.seconds
        if agent.genome.review:
            second = self._generate(agent, OWNER_REVIEW.format(draft=text, **fields), self.cfg.owner_tokens)
            text, seconds = second.text, seconds + second.seconds
        return Outcome(success=True, cost=seconds * self.cfg.cost_per_second, output=text, seconds=seconds)
