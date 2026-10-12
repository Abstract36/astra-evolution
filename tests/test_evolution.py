import random

import pytest

from astra.agent import Genome
from astra.config import EvolutionConfig, SandboxConfig
from astra.economy import Economy
from astra.evolution import EvolutionEngine, UnservedWork
from astra.population import Population
from astra.sandbox import Sandbox

MODELS = ["small", "medium"]


def setup(n=4, max_population=6, max_spawns=6, balance=100.0, **evo):
    sandbox = Sandbox(SandboxConfig(max_population=max_population, max_spawns_per_generation=max_spawns, owner_budget=1e6))
    economy = Economy(sandbox)
    population = Population()
    for _ in range(n):
        agent = population.spawn(Genome({"a": 1.0, "b": 0.0}, "small"))
        economy.fund(agent, balance, 0)
    cfg = EvolutionConfig(**evo)
    engine = EvolutionEngine(cfg, sandbox, economy, MODELS, random.Random(0))
    return population, economy, engine


def set_profits(population, profits):
    for agent, history in zip(population.alive(), profits):
        agent.history = list(history)


def test_bankrupt_agents_leave_even_without_evolution():
    population, economy, engine = setup()
    engine.enabled = False
    population.alive()[0].balance = -1
    events = engine.step(population, 0)
    assert events.bankrupt == [1] and len(population.alive()) == 3 and not events.births


def test_static_arm_never_reproduces():
    population, _, engine = setup()
    engine.enabled = False
    set_profits(population, [[10.0]] * 4)
    assert not engine.step(population, 0).births


def test_persistent_losers_are_defunded_into_treasury():
    population, economy, engine = setup(defund_after=2)
    set_profits(population, [[-1, -1], [-1, -1], [5, 5], [5, 5]])
    events = engine.step(population, 0, unserved=[])
    assert sorted(events.defunded) == [1, 2]
    assert economy.treasury == pytest.approx(200)


def test_losers_keep_funding_when_nobody_is_profitable():
    population, _, engine = setup(defund_after=2)
    set_profits(population, [[-1, -1]] * 4)
    assert not engine.step(population, 0).defunded


def test_children_follow_unserved_work_and_respect_limits():
    population, economy, engine = setup(n=2, max_population=6, max_spawns=3, payback_generations=10)
    set_profits(population, [[9.0], [9.0]])
    events = engine.step(population, 0, unserved=[("a", 0.5)] * 50, capacity=5)
    assert len(events.births) == 3  # spawn limit
    assert len(population.alive()) == 5
    for child_id, parents in events.births:
        child = population.get(child_id)
        assert child.balance == pytest.approx(engine.cfg.child_endowment)
        assert child.born == 1 and parents[0] in (1, 2)


def test_no_children_without_unserved_work_in_their_niche():
    population, _, engine = setup(n=2, payback_generations=10)
    set_profits(population, [[9.0], [9.0]])
    assert not engine.step(population, 0, unserved=[("b", 0.5)] * 50, capacity=5).births
    assert not engine.step(population, 0, unserved=[("a", 0.99)] * 50, capacity=5).births  # too hard for them


def test_parents_must_pay_back_a_child_in_time():
    population, _, engine = setup(n=2, payback_generations=10)  # child costs 30 -> needs 3 per generation
    set_profits(population, [[2.0], [2.0]])
    assert not engine.step(population, 0, unserved=[("a", 0.5)] * 50, capacity=5).births


def test_treasury_pays_when_parent_cannot():
    population, economy, engine = setup(n=3, balance=40.0, payback_generations=10, defund_after=1, reinvest_returned=True)
    set_profits(population, [[-1.0], [9.0], [9.0]])
    engine.step(population, 0, unserved=[("a", 0.5)] * 50, capacity=5)
    assert economy.reinvested > 0


def test_cull_replaces_the_weakest_when_full():
    population, _, engine = setup(n=6, max_population=6, cull_fraction=0.34, payback_generations=10)
    set_profits(population, [[1.0], [2.0], [9.0], [9.0], [9.0], [9.0]])
    events = engine.step(population, 0, unserved=[("a", 0.5)] * 50, capacity=5)
    assert sorted(events.outcompeted) == [1, 2]
    assert len(events.births) == 2 and len(population.alive()) == 6


def test_unserved_work_claims():
    population, _, _ = setup(n=1)
    work = UnservedWork([("a", 0.3)] * 3 + [("b", 0.3)], capacity=2)
    agent = population.alive()[0]
    assert work.has_room_for(agent)
    work.claim(agent)
    assert work.tasks == [("a", 0.3), ("b", 0.3)]


def test_lineage_follows_first_parents():
    population, _, engine = setup(n=2, max_population=6, payback_generations=10)
    set_profits(population, [[9.0], [9.0]])
    child_id, parents = engine.step(population, 0, unserved=[("a", 0.5)] * 50, capacity=5).births[0]
    assert population.lineage(child_id) == [parents[0]]


def test_targeted_children_are_built_for_harder_unserved_work():
    population, _, engine = setup(n=2, payback_generations=10, target_unserved=True)
    for agent in population.alive():
        agent.genome.max_difficulty = 0.4
    set_profits(population, [[9.0], [9.0]])
    events = engine.step(population, 0, unserved=[("a", 0.9)] * 50, capacity=5)
    assert events.births
    assert all(population.get(child).genome.max_difficulty >= 0.9 for child, _ in events.births)
