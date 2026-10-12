"""Money flows: owner funding, compute and upkeep costs, revenue and offspring.

All amounts are credits. In simulations they are virtual; in owner mode the
owner records real payments and real compute costs in the same unit.

Money taken back from defunded agents goes to a treasury. The treasury can
reinvest it in children of profitable agents, so funding moves from losing
strategies to winning ones without the owner adding a single credit.

Accounting identity (checked by the tests)::

    wealth = allocated + revenue - compute - upkeep - sales - spawn fees

where wealth is the sum of all agent balances plus the treasury.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .agent import Agent
from .sandbox import Sandbox

# Costs that count against an agent's operating profit (its fitness).
OPERATING = frozenset({"compute", "upkeep", "sales"})


@dataclass
class Transaction:
    generation: int
    agent_id: int
    kind: str
    amount: float  # signed, from the agent's point of view
    note: str = ""


class Economy:
    def __init__(self, sandbox: Sandbox, keep_ledger: bool = True):
        self.sandbox = sandbox
        self.keep_ledger = keep_ledger
        self.ledger: list[Transaction] = []
        self.allocated = 0.0   # owner money given to agents
        self.returned = 0.0    # money taken back from defunded agents
        self.reinvested = 0.0  # treasury money invested in new agents
        self.fees = 0.0        # spawn fees paid for new agents' infrastructure

    @property
    def treasury(self) -> float:
        return self.returned - self.reinvested

    def fund(self, agent: Agent, amount: float, generation: int) -> None:
        """Owner allocates money to an agent, within the owner budget."""
        self.sandbox.check_allocation(self.allocated, amount)
        self.allocated += amount
        self._post(agent, "funding", amount, generation)

    def charge(self, agent: Agent, amount: float, kind: str, generation: int, note: str = "") -> None:
        if amount < 0:
            raise ValueError("charges must be non-negative")
        self._post(agent, kind, -amount, generation, note)
        if kind in OPERATING:
            agent.gen_cost += amount
            agent.lifetime_cost += amount
        elif kind == "spawn_fee":
            self.fees += amount

    def pay(self, agent: Agent, amount: float, generation: int, note: str = "") -> None:
        """A client pays an agent for an accepted result."""
        if amount < 0:
            raise ValueError("payments must be non-negative")
        self._post(agent, "revenue", amount, generation, note)
        agent.gen_revenue += amount
        agent.lifetime_revenue += amount

    def transfer(self, src: Agent, dst: Agent, amount: float, generation: int) -> None:
        if amount > src.balance + 1e-9:
            raise ValueError(f"agent {src.id} cannot transfer {amount:g}, balance {src.balance:g}")
        self._post(src, "endowment_out", -amount, generation, f"to {dst.id}")
        self._post(dst, "endowment_in", amount, generation, f"from {src.id}")

    def invest(self, child: Agent, endowment: float, fee: float, generation: int, note: str = "") -> None:
        """Fund a new agent (endowment + spawn fee) from the treasury."""
        if endowment + fee > self.treasury + 1e-9:
            raise ValueError(f"treasury holds {self.treasury:g}, {endowment + fee:g} requested")
        self.reinvested += endowment + fee
        self.fees += fee
        self._post(child, "investment", endowment, generation, note)

    def withdraw(self, agent: Agent, generation: int, note: str = "") -> float:
        """Move an agent's remaining money to the treasury (used when defunding)."""
        amount = max(0.0, agent.balance)
        if amount:
            self._post(agent, "returned", -amount, generation, note)
            self.returned += amount
        return amount

    def wealth(self, agents: Iterable[Agent]) -> float:
        return sum(a.balance for a in agents) + self.treasury

    def _post(self, agent: Agent, kind: str, amount: float, generation: int, note: str = "") -> None:
        agent.balance += amount
        if self.keep_ledger:
            self.ledger.append(Transaction(generation, agent.id, kind, amount, note))

    def state(self) -> dict[str, float]:
        return {
            "allocated": self.allocated,
            "returned": self.returned,
            "reinvested": self.reinvested,
            "fees": self.fees,
        }

    def restore(self, state: dict[str, float]) -> None:
        self.allocated = state["allocated"]
        self.returned = state["returned"]
        self.reinvested = state["reinvested"]
        self.fees = state["fees"]

    def ledger_rows(self) -> list[dict]:
        return [asdict(t) for t in self.ledger]
