import pytest

from astra.agent import Agent, Genome
from astra.config import SandboxConfig
from astra.economy import Economy
from astra.sandbox import Sandbox, SandboxViolation


def agent(i=1):
    return Agent(i, Genome({"a": 1.0}, "small"))


@pytest.fixture
def economy():
    return Economy(Sandbox(SandboxConfig(owner_budget=100.0)))


def test_funding_respects_owner_budget(economy):
    economy.fund(agent(1), 60, 0)
    with pytest.raises(SandboxViolation):
        economy.fund(agent(2), 50, 0)


def test_operating_costs_and_revenue_feed_profit(economy):
    a = agent()
    economy.fund(a, 50, 0)
    a.begin_generation()
    economy.charge(a, 3, "compute", 0)
    economy.charge(a, 1, "upkeep", 0)
    economy.charge(a, 0.5, "sales", 0)
    economy.charge(a, 2, "spawn_fee", 0)  # not an operating cost
    economy.pay(a, 10, 0)
    assert a.end_generation() == pytest.approx(5.5)
    assert a.balance == pytest.approx(53.5)
    assert economy.fees == 2


def test_transfer_and_withdraw_into_treasury(economy):
    parent, child = agent(1), agent(2)
    economy.fund(parent, 50, 0)
    economy.transfer(parent, child, 20, 0)
    with pytest.raises(ValueError):
        economy.transfer(parent, child, 31, 0)
    assert economy.withdraw(child, 0) == 20
    assert child.balance == 0 and economy.treasury == 20
    assert economy.wealth([parent, child]) == pytest.approx(50)


def test_treasury_investment(economy):
    a, child = agent(1), agent(2)
    economy.fund(a, 40, 0)
    economy.withdraw(a, 0)
    economy.invest(child, 25, 5, 1)
    assert child.balance == 25 and economy.treasury == 10 and economy.fees == 5
    with pytest.raises(ValueError):
        economy.invest(agent(3), 25, 5, 1)
    assert economy.wealth([a, child]) == pytest.approx(40 - 5)


def test_negative_amounts_are_rejected(economy):
    with pytest.raises(ValueError):
        economy.charge(agent(), -1, "compute", 0)
    with pytest.raises(ValueError):
        economy.pay(agent(), -1, 0)


def test_state_roundtrip(economy):
    economy.fund(agent(), 10, 0)
    other = Economy(economy.sandbox)
    other.restore(economy.state())
    assert other.state() == economy.state()
