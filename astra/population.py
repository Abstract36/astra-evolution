"""The population: every agent that ever lived, plus summary statistics."""

from __future__ import annotations

from typing import Any, Iterable

from .agent import GENE_BOUNDS, Agent, Genome, Memory


class Population:
    def __init__(self) -> None:
        self._agents: dict[int, Agent] = {}
        self._next_id = 1

    def spawn(
        self,
        genome: Genome,
        *,
        reputation: float = 0.5,
        born: int = 0,
        parents: tuple[int, ...] = (),
        memory: Memory | None = None,
    ) -> Agent:
        agent = Agent(
            id=self._next_id,
            genome=genome,
            reputation=reputation,
            born=born,
            parents=parents,
            memory=memory or Memory(),
        )
        self._agents[agent.id] = agent
        self._next_id += 1
        return agent

    def get(self, agent_id: int) -> Agent:
        return self._agents[agent_id]

    def alive(self) -> list[Agent]:
        return [a for a in self._agents.values() if a.alive]

    def all(self) -> list[Agent]:
        return list(self._agents.values())

    def retire(self, agent: Agent, generation: int, reason: str) -> None:
        agent.alive = False
        agent.died = generation
        agent.death_reason = reason

    def lineage(self, agent_id: int) -> list[int]:
        """Ancestors along the first parent, nearest first."""
        chain = []
        current = self._agents[agent_id]
        while current.parents:
            parent_id = current.parents[0]
            chain.append(parent_id)
            current = self._agents[parent_id]
        return chain

    def to_dict(self) -> dict[str, Any]:
        return {"next_id": self._next_id, "agents": [a.to_dict() for a in self._agents.values()]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Population:
        population = cls()
        for item in data["agents"]:
            agent = Agent.from_dict(item)
            population._agents[agent.id] = agent
        population._next_id = data["next_id"]
        return population


def genome_stats(agents: Iterable[Agent], models: list[str], categories: list[str]) -> dict[str, float]:
    """Average strategy of a group of agents: what evolution is selecting for."""
    agents = list(agents)
    if not agents:
        return {}
    n = len(agents)
    stats: dict[str, float] = {}
    for gene in GENE_BOUNDS:
        stats[f"gene:{gene}"] = sum(getattr(a.genome, gene) for a in agents) / n
    stats["gene:review"] = sum(a.genome.review for a in agents) / n
    stats["specialization"] = sum(max(a.genome.focus.values()) for a in agents) / n
    for m in models:
        stats[f"model:{m}"] = sum(a.genome.model == m for a in agents) / n
    for c in categories:
        stats[f"focus:{c}"] = sum(a.genome.focus.get(c, 0.0) for a in agents) / n
    return stats
