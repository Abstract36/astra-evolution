import random

import pytest

from astra.agent import Agent, Genome
from astra.config import AgentSettings, MarketConfig, SandboxConfig, ShockSpec
from astra.economy import Economy
from astra.market import SimulatedMarket, Task, WinModel, client_score, trade_round
from astra.sandbox import Sandbox
from astra.solvers import Outcome


class AlwaysSucceeds:
    def estimate_cost(self, agent, task):
        return 1.0

    def attempt(self, agent, task, rng):
        return Outcome(True, 1.0)


def specialist(i, price_level=0.8, reputation=0.5, category="a"):
    g = Genome({"a": 1.0 if category == "a" else 0.0, "b": 1.0 if category == "b" else 0.0}, "small")
    g.price_level, g.max_difficulty, g.min_confidence = price_level, 1.0, 0.0
    return Agent(i, g, balance=100.0, reputation=reputation)


def task(i=0, category="a", competitor=None):
    return Task(f"t{i}", 0, category, 0.5, 1.0, 10.0, competitor)


def run(tasks, agents, **market):
    cfg = MarketConfig(**{"agent_capacity": 5, **market})
    economy = Economy(Sandbox(SandboxConfig()))
    stats = trade_round(
        tasks, agents, AlwaysSucceeds(), economy, AgentSettings(), cfg, 0.2, random.Random(0), 0, win_model=WinModel()
    )
    return stats


def test_market_is_reproducible_and_demand_stays_normalized():
    cfg = MarketConfig(tasks_per_generation=30)
    a, b = SimulatedMarket(cfg, random.Random(4)), SimulatedMarket(cfg, random.Random(4))
    for g in range(5):
        ta, tb = a.tasks_for(g), b.tasks_for(g)
        assert [(t.category, t.difficulty, t.max_price) for t in ta] == [(t.category, t.difficulty, t.max_price) for t in tb]
        assert sum(a.demand.values()) == pytest.approx(1.0)
        assert all(0.05 <= t.difficulty <= 0.98 and t.competitor_price < t.max_price + 1e-9 for t in ta)


def test_shock_moves_demand():
    cfg = MarketConfig(demand_drift=0.0, shocks=[ShockSpec(2, "automation", 10.0)])
    market = SimulatedMarket(cfg, random.Random(0))
    before = market.demand["automation"]
    market.tasks_for(0), market.tasks_for(1), market.tasks_for(2)
    assert market.demand["automation"] > 2 * before


def test_firm_mode_sends_one_offer_and_prefers_expected_profit():
    cheap, dear = specialist(1, price_level=0.5), specialist(2, price_level=0.9)
    stats = run([task()], [cheap, dear])
    assert stats.assigned == 1 and stats.succeeded == 1
    assert dear.tasks_done == 1 and cheap.tasks_done == 0
    assert stats.revenue == pytest.approx(9.0)


def test_internal_competition_lets_the_client_pick_value_for_money():
    cheap, dear = specialist(1, price_level=0.5), specialist(2, price_level=0.9)
    run([task()], [cheap, dear], internal_competition=True)
    assert cheap.tasks_done == 1 and dear.tasks_done == 0


def test_outside_competitor_can_win():
    stats = run([task(competitor=1.0)], [specialist(1, price_level=0.9)])
    assert stats.lost_to_competitors == 1 and stats.assigned == 0


def test_capacity_and_unserved_work():
    a = specialist(1)
    stats = run([task(i) for i in range(4)] + [task(9, category="b")], [a], agent_capacity=2)
    assert a.tasks_done == 2
    assert stats.unbid == 3
    assert ("b", 0.5) in stats.unserved


def test_win_model_learns():
    model = WinModel(prior=0.5, weight=2)
    for _ in range(8):
        model.record(1.0, True)
        model.record(0.5, False)
    assert model.probability(1.0) > 0.8 > 0.2 > model.probability(0.5)


def test_client_score_prefers_trust_and_low_price():
    t = task()
    assert client_score(0.9, 5, t) > client_score(0.5, 5, t) > client_score(0.5, 8, t)
