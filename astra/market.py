"""Tasks, the simulated market and the auction that assigns tasks to agents."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from .agent import Agent, Bid, normalize
from .config import AgentSettings, MarketConfig

if TYPE_CHECKING:
    from .economy import Economy
    from .solvers import Outcome, Solver


@dataclass
class Task:
    id: str
    generation: int
    category: str
    difficulty: float  # 0..1
    size: float        # amount of work; scales cost and price
    max_price: float   # the most the client will pay
    competitor_price: float | None = None  # best outside offer, if any
    payload: dict[str, Any] = field(default_factory=dict)


class SimulatedMarket:
    """Clients posting tasks. Demand per category drifts and can be shocked."""

    def __init__(self, cfg: MarketConfig, rng: random.Random):
        self.cfg = cfg
        self.rng = rng
        self.specs = {c.name: c for c in cfg.categories}
        self.demand = normalize({c.name: c.demand for c in cfg.categories})

    @property
    def categories(self) -> list[str]:
        return list(self.specs)

    def tasks_for(self, generation: int) -> list[Task]:
        if generation > 0 and self.cfg.demand_drift > 0:
            self.demand = normalize(
                {
                    c: w * math.exp(self.rng.gauss(0.0, self.cfg.demand_drift))
                    for c, w in self.demand.items()
                }
            )
        for shock in self.cfg.shocks:
            if shock.generation == generation:
                self.demand[shock.category] *= shock.multiplier
                self.demand = normalize(self.demand)

        names = list(self.demand)
        weights = [self.demand[c] for c in names]
        lo, hi = self.cfg.size_range
        tasks = []
        for i in range(self.cfg.tasks_per_generation):
            category = self.rng.choices(names, weights)[0]
            spec = self.specs[category]
            difficulty = min(0.98, max(0.05, self.rng.gauss(spec.difficulty, 0.15)))
            size = self.rng.uniform(lo, hi)
            max_price = size * spec.pay_rate * (0.5 + difficulty)
            competitor = None
            if self.cfg.external_competition:
                competitor = max_price * self.rng.uniform(*self.cfg.competitor_price_range)
            tasks.append(
                Task(f"g{generation}-t{i}", generation, category, difficulty, size, max_price, competitor)
            )
        return tasks


def client_score(reputation: float, price: float, task: Task) -> float:
    """Value for money as the client sees it: trust per unit of price."""
    return (reputation + 0.25) * task.max_price / max(price, 1e-9)


class WinModel:
    """Shared knowledge of the population: how often clients accept an offer,
    as a function of the offer's value-for-money score (binned)."""

    def __init__(self, prior: float = 0.5, weight: float = 2.0, bin_width: float = 0.1):
        self.prior = prior
        self.weight = weight
        self.bin_width = bin_width
        self.offers: dict[int, float] = {}
        self.wins: dict[int, float] = {}

    def _bin(self, score: float) -> int:
        return int(score / self.bin_width)

    def probability(self, score: float) -> float:
        b = self._bin(score)
        return (self.wins.get(b, 0.0) + self.prior * self.weight) / (self.offers.get(b, 0.0) + self.weight)

    def record(self, score: float, won: bool) -> None:
        b = self._bin(score)
        self.offers[b] = self.offers.get(b, 0.0) + 1
        self.wins[b] = self.wins.get(b, 0.0) + (1 if won else 0)


@dataclass
class RoundStats:
    offered: int = 0
    unbid: int = 0
    lost_to_competitors: int = 0
    assigned: int = 0
    succeeded: int = 0
    revenue: float = 0.0
    compute_cost: float = 0.0
    sales_cost: float = 0.0
    unserved: list[tuple[str, float]] = field(default_factory=list)  # (category, difficulty)


def select_bid(
    bids: list[Bid], task: Task, rng: random.Random, internal_competition: bool = False
) -> tuple[Bid, float]:
    """Pick the population's offer for ``task`` and return it with the client's score.

    By default the population acts as one firm: it puts forward the single bid
    with the highest expected profit (see ``Agent.decide_bid``). With
    ``internal_competition`` every agent bids on its own and the client picks
    the best value for money, so agents can undercut each other.
    """
    if internal_competition:
        key = lambda b: client_score(b.agent.reputation, b.price, task)  # noqa: E731
    else:
        key = lambda b: b.expected_profit  # noqa: E731
    _, _, best = max(((key(b), rng.random(), b) for b in bids), key=lambda s: (s[0], s[1]))
    return best, client_score(best.agent.reputation, best.price, task)


def trade_round(
    tasks: list[Task],
    agents: list[Agent],
    solver: Solver,
    economy: Economy,
    settings: AgentSettings,
    market_cfg: MarketConfig,
    reputation_alpha: float,
    rng: random.Random,
    generation: int,
    on_attempt: Callable[[Task, Bid, Outcome], None] | None = None,
    bid_cost: float = 0.0,
    win_model: WinModel | None = None,
) -> RoundStats:
    """Auction every task, let the winner attempt it and settle the money.

    Every offer put in front of a client costs ``bid_cost`` (preparing a
    proposal is work), so offers that clients turn down are not free.
    """
    stats = RoundStats(offered=len(tasks))
    load = {a.id: 0 for a in agents}
    win_probability = win_model.probability if win_model is not None else None
    for task in tasks:
        bids = []
        for agent in agents:
            if load[agent.id] >= market_cfg.agent_capacity:
                continue
            bid = agent.decide_bid(
                task, solver.estimate_cost(agent, task), settings, bid_cost, win_probability
            )
            if bid is not None:
                bids.append(bid)
        if not bids:
            stats.unbid += 1
            stats.unserved.append((task.category, task.difficulty))
            continue
        best, score = select_bid(bids, task, rng, market_cfg.internal_competition)
        offers = bids if market_cfg.internal_competition else [best]
        won = task.competitor_price is None or score >= client_score(
            market_cfg.competitor_reputation, task.competitor_price, task
        )
        for offer in offers:
            if bid_cost > 0:
                economy.charge(offer.agent, bid_cost, "sales", generation, task.id)
                stats.sales_cost += bid_cost
            if win_model is not None:
                offer_score = client_score(offer.agent.reputation, offer.price, task)
                win_model.record(offer_score, won and offer is best)
        if not won:
            stats.lost_to_competitors += 1
            continue

        agent = best.agent
        outcome = solver.attempt(agent, task, rng)
        economy.charge(agent, outcome.cost, "compute", generation, task.id)
        agent.record_attempt(task.category, outcome.success, outcome.cost, reputation_alpha)
        if outcome.success:
            economy.pay(agent, best.price, generation, task.id)
            stats.succeeded += 1
            stats.revenue += best.price
        stats.assigned += 1
        stats.compute_cost += outcome.cost
        load[agent.id] += 1
        if on_attempt is not None:
            on_attempt(task, best, outcome)
    return stats
