"""Selection, reproduction and mutation.

After every generation:

1. Agents that ran out of money are retired (``bankrupt``). This applies to
   every arm: nobody can spend money they do not have.
2. With evolution enabled, agents that lost money ``defund_after`` generations
   in a row lose their funding (``defunded``) as long as profitable agents
   exist to take over. Their remaining money goes to the treasury.
3. When the population is at its limit, the weakest ``cull_fraction`` of agents
   are defunded (``outcompeted``), but only as many as can actually be replaced.
4. Agents whose profit pays back the cost of a child within
   ``payback_generations`` create children, but only when the market left
   work unserved that a copy of them could actually do (their main category,
   no harder than they accept). Without this check, clones crowd a saturated
   niche and starve each other, a classic failure of evolutionary search.
   The parent pays the spawn fee and the child's endowment from its own
   earnings; if it cannot, the treasury may invest instead
   (``reinvest_returned``), so money moves from losing strategies to winning
   ones without the owner adding any.

Children inherit a mutated (and sometimes crossed-over) genome plus a
discounted copy of the parent's memory and reputation. The sandbox caps the
population size and the number of spawns per generation.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .agent import Agent
from .config import EvolutionConfig
from .economy import Economy
from .population import Population
from .sandbox import Sandbox


@dataclass
class GenerationEvents:
    bankrupt: list[int] = field(default_factory=list)
    defunded: list[int] = field(default_factory=list)
    outcompeted: list[int] = field(default_factory=list)
    births: list[tuple[int, tuple[int, ...]]] = field(default_factory=list)  # (child, parents)
    invested: float = 0.0  # treasury money put into new agents


class UnservedWork:
    """Tasks nobody bid on in the last generation: the room a new agent could fill."""

    def __init__(self, tasks: list[tuple[str, float]], capacity: int):
        self.tasks = list(tasks)  # (category, difficulty)
        self.capacity = capacity

    def _matching(self, agent: Agent) -> list[int]:
        g = agent.genome
        return [i for i, (c, d) in enumerate(self.tasks) if c == g.specialty and d <= g.max_difficulty]

    def has_room_for(self, agent: Agent) -> bool:
        """Enough unserved work to keep a copy of ``agent`` at least half busy."""
        return len(self._matching(agent)) >= max(1, self.capacity // 2)

    def claim(self, agent: Agent) -> None:
        for i in reversed(self._matching(agent)[: self.capacity]):
            del self.tasks[i]


class EvolutionEngine:
    def __init__(
        self,
        cfg: EvolutionConfig,
        sandbox: Sandbox,
        economy: Economy,
        models: list[str],
        rng: random.Random,
        *,
        enabled: bool = True,
        initial_reputation: float = 0.5,
    ):
        self.cfg = cfg
        self.sandbox = sandbox
        self.economy = economy
        self.models = models
        self.rng = rng
        self.enabled = enabled
        self.initial_reputation = initial_reputation

    @property
    def child_price(self) -> float:
        return self.cfg.spawn_cost + self.cfg.child_endowment

    def step(
        self,
        population: Population,
        generation: int,
        unserved: list[tuple[str, float]] | None = None,
        capacity: int = 1,
    ) -> GenerationEvents:
        """Run selection after ``generation``.

        ``unserved`` lists the (category, difficulty) of tasks nobody bid on;
        None means growth is not limited by demand (owner mode).
        """
        events = GenerationEvents()
        for agent in population.alive():
            if agent.balance <= 0:
                population.retire(agent, generation, "bankrupt")
                events.bankrupt.append(agent.id)
        if not self.enabled:
            return events

        losers = [a for a in population.alive() if a.loss_streak() >= self.cfg.defund_after]
        others = [a for a in population.alive() if a not in losers]
        if losers and any(self.fitness(a) > 0 for a in others if a.history):
            # With no profitable agent around, losers keep running until money runs out.
            for agent in losers:
                self._defund(population, agent, generation, "defunded")
                events.defunded.append(agent.id)
        work = None if unserved is None else UnservedWork(unserved, capacity)
        self._cull(population, generation, events, work)
        self._reproduce(population, generation, events, work)
        return events

    def fitness(self, agent: Agent) -> float:
        return agent.fitness(self.cfg.fitness_window)

    def affordable_children(self, agent: Agent) -> int:
        """Children the agent can pay for from its own money."""
        return max(0, int((agent.balance - self.cfg.parent_reserve) // self.child_price))

    def treasury_children(self) -> int:
        """Children the treasury can pay for."""
        if not self.cfg.reinvest_returned:
            return 0
        return max(0, int(self.economy.treasury // self.child_price))

    def eligible_parents(self, agents: list[Agent], work: UnservedWork | None = None) -> list[Agent]:
        """Agents whose profit pays back a child in time and whose copy would find work."""
        threshold = self.child_price / self.cfg.payback_generations
        return [
            a
            for a in agents
            if a.history and self.fitness(a) >= threshold and (work is None or work.has_room_for(a))
        ]

    def _defund(self, population: Population, agent: Agent, generation: int, reason: str) -> None:
        self.economy.withdraw(agent, generation, reason)
        population.retire(agent, generation, reason)

    def _cull(
        self, population: Population, generation: int, events: GenerationEvents, work: UnservedWork | None
    ) -> None:
        alive = population.alive()
        if self.cfg.cull_fraction <= 0 or len(alive) < self.sandbox.max_population:
            return
        k = max(1, round(len(alive) * self.cfg.cull_fraction))
        victims = sorted((a for a in alive if a.history), key=self.fitness)[:k]
        survivors = [a for a in alive if a not in victims]
        parents = self.eligible_parents(survivors, work)
        if not parents:
            return
        funded = sum(self.affordable_children(a) for a in parents) + self.treasury_children()
        replaceable = min(funded, len(parents), self.sandbox.cfg.max_spawns_per_generation)
        for agent in victims[:replaceable]:
            self._defund(population, agent, generation, "outcompeted")
            events.outcompeted.append(agent.id)

    def _tournament(self, candidates: list[Agent]) -> Agent:
        size = min(self.cfg.tournament_size, len(candidates))
        return max(self.rng.sample(candidates, size), key=self.fitness)

    def _reproduce(
        self, population: Population, generation: int, events: GenerationEvents, work: UnservedWork | None
    ) -> None:
        free = self.sandbox.max_population - len(population.alive())
        slots = min(free, self.sandbox.cfg.max_spawns_per_generation)
        parents = self.eligible_parents(population.alive(), work)
        spawned = 0
        while spawned < slots and parents:
            parent = self._tournament(parents)
            if work is not None and not work.has_room_for(parent):
                parents.remove(parent)
                continue
            if self.affordable_children(parent) >= 1:
                payer = "parent"
            elif self.treasury_children() >= 1:
                payer = "treasury"
            else:
                parents.remove(parent)
                continue
            others = [a for a in parents if a is not parent]
            partner = None
            if others and self.rng.random() < self.cfg.crossover_rate:
                partner = self._tournament(others)
            self.sandbox.check_population(len(population.alive()))
            self.sandbox.check_spawn(spawned)
            if work is not None:
                work.claim(parent)
            child = self._spawn_child(population, parent, partner, generation, payer)
            if payer == "treasury":
                events.invested += self.child_price
            events.births.append((child.id, child.parents))
            spawned += 1

    def _spawn_child(
        self, population: Population, parent: Agent, partner: Agent | None, generation: int, payer: str
    ) -> Agent:
        genome = parent.genome.crossover(partner.genome, self.rng) if partner else parent.genome
        genome = genome.mutated(self.rng, self.cfg.mutation_rate, self.cfg.mutation_scale, self.models)
        inherit = self.cfg.reputation_inheritance
        reputation = self.initial_reputation + inherit * (parent.reputation - self.initial_reputation)
        child = population.spawn(
            genome,
            reputation=reputation,
            born=generation + 1,
            parents=(parent.id,) + ((partner.id,) if partner else ()),
            memory=parent.memory.inherited(self.cfg.memory_inheritance),
        )
        if payer == "parent":
            self.economy.charge(parent, self.cfg.spawn_cost, "spawn_fee", generation, f"child {child.id}")
            self.economy.transfer(parent, child, self.cfg.child_endowment, generation)
        else:
            self.economy.invest(
                child, self.cfg.child_endowment, self.cfg.spawn_cost, generation, f"child of {parent.id}"
            )
        parent.children += 1
        return child
