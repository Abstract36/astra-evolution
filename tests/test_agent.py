import random

import pytest

from astra.agent import GENE_BOUNDS, Agent, Genome, Memory
from astra.config import AgentSettings
from astra.market import Task

CATS = ["a", "b", "c"]
MODELS = ["small", "medium", "large"]


def make_task(category="a", difficulty=0.5, max_price=10.0):
    return Task("t", 0, category, difficulty, 1.0, max_price)


def specialist(category="a", **genes):
    focus = {c: 1.0 if c == category else 0.0 for c in CATS}
    return Genome(focus=focus, model="small", **genes)


def assert_valid(g: Genome):
    for gene, (lo, hi) in GENE_BOUNDS.items():
        assert lo <= getattr(g, gene) <= hi
    assert sum(g.focus.values()) == pytest.approx(1.0)
    assert min(g.focus.values()) >= 0
    assert g.model in MODELS


def test_random_genomes_are_valid_and_reproducible():
    a = [Genome.random(CATS, MODELS, random.Random(5)) for _ in range(2)]
    assert a[0] == a[1]
    for _ in range(50):
        assert_valid(Genome.random(CATS, MODELS, random.Random(_)))


def test_mutation_stays_in_bounds_and_changes_something():
    rng = random.Random(1)
    g = Genome.random(CATS, MODELS, rng)
    children = [g.mutated(rng, rate=1.0, scale=0.5, models=MODELS) for _ in range(100)]
    for child in children:
        assert_valid(child)
    assert any(c != g for c in children)
    assert g.mutated(rng, rate=0.0, scale=0.5, models=MODELS) == g


def test_mutation_replaces_unknown_model():
    g = specialist()
    g.model = "removed"
    assert g.mutated(random.Random(0), 0.0, 0.1, MODELS).model in MODELS


def test_crossover_takes_genes_from_parents():
    rng = random.Random(2)
    a, b = specialist("a", effort=0.5), specialist("b", effort=2.0)
    for _ in range(20):
        child = a.crossover(b, rng)
        assert child.effort in (0.5, 2.0)
        assert child.focus["c"] == 0.0
        assert sum(child.focus.values()) == pytest.approx(1.0)


def test_with_categories_adds_missing_categories():
    g = specialist("a").with_categories(CATS + ["d"])
    assert set(g.focus) == {"a", "b", "c", "d"}
    assert g.focus["d"] > 0 and sum(g.focus.values()) == pytest.approx(1.0)


def test_genome_and_agent_roundtrip():
    agent = Agent(7, Genome.random(CATS, MODELS, random.Random(3)), balance=12.5, parents=(1, 2))
    agent.memory.record("a", True, 1.5)
    agent.history = [1.0, -2.0]
    restored = Agent.from_dict(agent.to_dict())
    assert restored.to_dict() == agent.to_dict()


def test_memory_estimates_and_inheritance():
    m = Memory()
    assert m.success_estimate("a", prior=0.6, weight=2) == pytest.approx(0.6)
    for ok in (True, True, False, True):
        m.record("a", ok, 2.0)
    assert m.success_estimate("a", prior=0.6, weight=2) == pytest.approx((3 + 1.2) / 6)
    assert m.mean_cost("a") == pytest.approx(2.0)
    assert m.mean_cost("b") is None
    child = m.inherited(0.5)
    assert child.attempts("a") == 2 and child.mean_cost("a") == pytest.approx(2.0)


class TestBidding:
    settings = AgentSettings(exploration_trials=0, prior_success=0.9)

    def agent(self, **genes):
        genes = {"price_level": 0.8, "max_difficulty": 0.7, "min_confidence": 0.5, **genes}
        return Agent(1, specialist("a", **genes), balance=100.0)

    def test_bids_on_a_good_task(self):
        bid = self.agent().decide_bid(make_task(), 2.0, self.settings)
        assert bid is not None
        assert bid.price == pytest.approx(8.0)
        assert bid.expected_profit == pytest.approx(0.9 * 8.0 - 2.0)

    @pytest.mark.parametrize(
        "task, cost, genes",
        [
            (make_task(difficulty=0.9), 2.0, {}),         # too hard for its risk appetite
            (make_task(category="b"), 2.0, {}),           # outside its specialization
            (make_task(), 200.0, {}),                     # cannot afford the compute
            (make_task(), 9.0, {}),                       # price would not cover the cost
            (make_task(), 2.0, {"min_confidence": 0.95}), # not confident enough
        ],
    )
    def test_declines(self, task, cost, genes):
        assert self.agent(**genes).decide_bid(task, cost, self.settings) is None

    def test_low_win_probability_makes_bid_unprofitable(self):
        bid = self.agent().decide_bid(make_task(), 2.0, self.settings, bid_cost=0.5, win_probability=lambda s: 0.01)
        assert bid is None

    def test_exploration_ignores_confidence(self):
        settings = AgentSettings(exploration_trials=2, prior_success=0.1)
        assert self.agent().decide_bid(make_task(), 2.0, settings) is not None


def test_reputation_and_loss_streak():
    agent = Agent(1, specialist(), reputation=0.5)
    agent.record_attempt("a", True, 1.0, reputation_alpha=0.5)
    assert agent.reputation == pytest.approx(0.75)
    agent.history = [3.0, -1.0, -2.0]
    assert agent.loss_streak() == 2
    assert agent.fitness(2) == pytest.approx(-1.5)
