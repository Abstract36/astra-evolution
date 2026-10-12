"""Agents and their heritable strategies.

The genome is what a child inherits (with mutations). Memory and reputation are
acquired during an agent's life; a child starts with a discounted copy of both.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .config import AgentSettings
    from .market import Task

# Allowed range of every continuous gene.
GENE_BOUNDS: dict[str, tuple[float, float]] = {
    "effort": (0.5, 2.0),            # compute multiplier: costs more, improves quality
    "price_level": (0.3, 1.0),       # price as a share of the client's budget
    "max_difficulty": (0.1, 1.0),    # risk appetite: hardest task the agent bids on
    "min_confidence": (0.05, 0.85),  # minimum estimated success rate to bid
}


def normalize(weights: dict[str, float]) -> dict[str, float]:
    clipped = {k: max(0.0, v) for k, v in weights.items()}
    total = sum(clipped.values())
    if total <= 0:
        share = 1.0 / len(clipped)
        return {k: share for k in clipped}
    return {k: v / total for k, v in clipped.items()}


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, value))


@dataclass
class Genome:
    """A strategy: what to work on, with which model, how hard and at what price.

    Prices are set relative to what the work is worth to the client
    (``price_level`` x client budget), not as a markup on cost, so an agent
    that finds a cheaper way to do the same work keeps the saving.

    ``focus`` spreads a fixed amount of specialization over task categories
    (weights sum to 1): specialists are strong in few categories, generalists
    are mediocre in many.
    """

    focus: dict[str, float]
    model: str
    effort: float = 1.0
    price_level: float = 0.7
    max_difficulty: float = 0.7
    min_confidence: float = 0.4
    review: bool = False

    @classmethod
    def random(cls, categories: list[str], models: list[str], rng: random.Random) -> Genome:
        focus = normalize({c: rng.gammavariate(0.7, 1.0) for c in categories})
        model = rng.choice(models)
        genes = {gene: rng.uniform(lo, hi) for gene, (lo, hi) in GENE_BOUNDS.items()}
        return cls(focus=focus, model=model, review=rng.random() < 0.5, **genes)

    def copy(self) -> Genome:
        return Genome(
            focus=dict(self.focus),
            model=self.model,
            effort=self.effort,
            price_level=self.price_level,
            max_difficulty=self.max_difficulty,
            min_confidence=self.min_confidence,
            review=self.review,
        )

    def mutated(self, rng: random.Random, rate: float, scale: float, models: list[str]) -> Genome:
        """Return a copy where each gene changes with probability ``rate``."""
        child = self.copy()
        for gene, (lo, hi) in GENE_BOUNDS.items():
            if rng.random() < rate:
                value = getattr(child, gene) + rng.gauss(0.0, scale * (hi - lo))
                setattr(child, gene, _clamp(value, lo, hi))
        if rng.random() < rate:
            focus = {c: w * math.exp(rng.gauss(0.0, 2 * scale)) + 1e-3 for c, w in child.focus.items()}
            if rng.random() < 0.25:  # occasional jump into another niche
                focus[rng.choice(sorted(focus))] += 0.3
            child.focus = normalize(focus)
        if child.model not in models:
            child.model = rng.choice(models)
        elif len(models) > 1 and rng.random() < rate / 2:
            i = models.index(child.model) + rng.choice((-1, 1))
            child.model = models[int(_clamp(i, 0, len(models) - 1))]
        if rng.random() < rate / 3:
            child.review = not child.review
        return child

    def crossover(self, other: Genome, rng: random.Random) -> Genome:
        """Uniform crossover; focus is a random blend of both parents."""

        def pick(a: Any, b: Any) -> Any:
            return a if rng.random() < 0.5 else b

        t = rng.random()
        categories = sorted(set(self.focus) | set(other.focus))
        focus = normalize(
            {c: t * self.focus.get(c, 0.0) + (1 - t) * other.focus.get(c, 0.0) for c in categories}
        )
        return Genome(
            focus=focus,
            model=pick(self.model, other.model),
            effort=pick(self.effort, other.effort),
            price_level=pick(self.price_level, other.price_level),
            max_difficulty=pick(self.max_difficulty, other.max_difficulty),
            min_confidence=pick(self.min_confidence, other.min_confidence),
            review=pick(self.review, other.review),
        )

    def with_categories(self, categories: list[str]) -> Genome:
        """Copy that also covers new categories (each gets an equal small share)."""
        child = self.copy()
        missing = [c for c in categories if c not in child.focus]
        if missing:
            share = 1.0 / (len(child.focus) + len(missing))
            child.focus = normalize({**child.focus, **{c: share for c in missing}})
        return child

    @property
    def specialty(self) -> str:
        return max(self.focus, key=lambda c: self.focus[c])

    def to_dict(self) -> dict[str, Any]:
        return {
            "focus": dict(self.focus),
            "model": self.model,
            "effort": self.effort,
            "price_level": self.price_level,
            "max_difficulty": self.max_difficulty,
            "min_confidence": self.min_confidence,
            "review": self.review,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Genome:
        data = dict(data)
        data["focus"] = dict(data["focus"])
        return cls(**data)


@dataclass
class CategoryStats:
    attempts: float = 0.0
    successes: float = 0.0
    cost: float = 0.0


class Memory:
    """What an agent has learned about its own performance, per task category."""

    def __init__(self, stats: dict[str, CategoryStats] | None = None):
        self.stats: dict[str, CategoryStats] = stats or {}

    def record(self, category: str, success: bool, cost: float) -> None:
        s = self.stats.setdefault(category, CategoryStats())
        s.attempts += 1
        s.successes += 1 if success else 0
        s.cost += cost

    def attempts(self, category: str) -> float:
        s = self.stats.get(category)
        return s.attempts if s else 0.0

    def success_estimate(self, category: str, prior: float, weight: float) -> float:
        """Posterior mean of the success rate, starting from ``prior``."""
        s = self.stats.get(category)
        attempts, successes = (s.attempts, s.successes) if s else (0.0, 0.0)
        return (successes + prior * weight) / (attempts + weight)

    def mean_cost(self, category: str) -> float | None:
        s = self.stats.get(category)
        return s.cost / s.attempts if s and s.attempts > 0 else None

    def inherited(self, factor: float) -> Memory:
        return Memory(
            {
                c: CategoryStats(s.attempts * factor, s.successes * factor, s.cost * factor)
                for c, s in self.stats.items()
            }
        )

    def to_dict(self) -> dict[str, list[float]]:
        return {c: [s.attempts, s.successes, s.cost] for c, s in self.stats.items()}

    @classmethod
    def from_dict(cls, data: dict[str, list[float]]) -> Memory:
        return cls({c: CategoryStats(*values) for c, values in data.items()})


@dataclass
class Bid:
    agent: Agent
    price: float
    confidence: float
    estimated_cost: float
    expected_profit: float = 0.0


@dataclass
class Agent:
    id: int
    genome: Genome
    balance: float = 0.0
    reputation: float = 0.5
    born: int = 0
    parents: tuple[int, ...] = ()
    memory: Memory = field(default_factory=Memory)
    alive: bool = True
    died: int | None = None
    death_reason: str | None = None
    children: int = 0
    history: list[float] = field(default_factory=list)  # operating profit per generation
    lifetime_revenue: float = 0.0
    lifetime_cost: float = 0.0
    tasks_done: int = 0
    tasks_succeeded: int = 0
    gen_revenue: float = 0.0
    gen_cost: float = 0.0

    def begin_generation(self) -> None:
        self.gen_revenue = 0.0
        self.gen_cost = 0.0

    def end_generation(self) -> float:
        profit = self.gen_revenue - self.gen_cost
        self.history.append(profit)
        return profit

    def fitness(self, window: int) -> float:
        """Mean operating profit over the last ``window`` generations."""
        recent = self.history[-window:]
        return sum(recent) / len(recent) if recent else 0.0

    def loss_streak(self) -> int:
        streak = 0
        for profit in reversed(self.history):
            if profit >= 0:
                break
            streak += 1
        return streak

    def decide_bid(
        self,
        task: Task,
        estimated_cost: float,
        settings: AgentSettings,
        bid_cost: float = 0.0,
        win_probability: Callable[[float], float] | None = None,
    ) -> Bid | None:
        """Bid on ``task`` if the genome says it is worth it, else return None.

        Expected profit = P(client accepts) x (P(success) x price - cost) - bid cost.
        P(success) comes from the agent's own (and inherited) memory; P(client
        accepts) from what the whole population has learned about clients
        (``win_probability`` of the client's value-for-money score).
        """
        g = self.genome
        if task.difficulty > g.max_difficulty:
            return None
        if g.focus.get(task.category, 0.0) < settings.min_focus_to_bid:
            return None
        if estimated_cost > self.balance:
            return None
        price = task.max_price * g.price_level
        if price <= estimated_cost:
            return None
        confidence = self.memory.success_estimate(
            task.category, settings.prior_success, settings.prior_weight
        )
        win = 1.0
        if win_probability is not None:
            win = win_probability((self.reputation + 0.25) * task.max_price / price)
        expected = win * (confidence * price - estimated_cost) - bid_cost
        exploring = self.memory.attempts(task.category) < settings.exploration_trials
        if not exploring and (confidence < g.min_confidence or expected <= 0):
            return None
        return Bid(self, price, confidence, estimated_cost, expected)

    def record_attempt(self, category: str, success: bool, cost: float, reputation_alpha: float) -> None:
        self.memory.record(category, success, cost)
        self.tasks_done += 1
        self.tasks_succeeded += 1 if success else 0
        target = 1.0 if success else 0.0
        self.reputation += reputation_alpha * (target - self.reputation)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "genome": self.genome.to_dict(),
            "balance": self.balance,
            "reputation": self.reputation,
            "born": self.born,
            "parents": list(self.parents),
            "memory": self.memory.to_dict(),
            "alive": self.alive,
            "died": self.died,
            "death_reason": self.death_reason,
            "children": self.children,
            "history": list(self.history),
            "lifetime_revenue": self.lifetime_revenue,
            "lifetime_cost": self.lifetime_cost,
            "tasks_done": self.tasks_done,
            "tasks_succeeded": self.tasks_succeeded,
            "gen_revenue": self.gen_revenue,
            "gen_cost": self.gen_cost,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Agent:
        data = dict(data)
        genome = Genome.from_dict(data.pop("genome"))
        memory = Memory.from_dict(data.pop("memory"))
        parents = tuple(data.pop("parents"))
        return cls(genome=genome, memory=memory, parents=parents, **data)
