"""A simple learning router: the baseline evolution has to beat.

One firm with one wallet and a fixed menu of ways to do the work: every task
category x model x effort x price level x review setting. For each task it
picks the option with the highest *sampled* expected profit, with success
rates learned per option and per difficulty band of the task (a contextual
Thompson-sampling bandit), and learns from the outcome.
Nothing is inherited, mutated or selected. If this does as well as
evolution, the evolutionary machinery is not worth its complexity.

To keep the comparison fair, the router gets the same capital, pays the same
upkeep and has the same capacity (tasks per generation) as a full population
of ``experiment.population_size`` agents, each option keeps its own
reputation with clients as each agent does, and it competes for the same
tasks against the same outside competitor.
"""

from __future__ import annotations

import itertools
import random
from typing import TYPE_CHECKING

from .agent import Agent, Genome
from .config import Config
from .economy import Economy
from .market import RoundStats, Task, WinModel, client_score
from .population import Population
from .sandbox import Sandbox
from .solvers import Solver

if TYPE_CHECKING:
    from .experiment import ArmResult, Market, Progress


def menu_genomes(cfg: Config, categories: list[str], models: list[str]) -> list[Genome]:
    r = cfg.router
    return [
        Genome(
            focus={c: 1.0 if c == category else 0.0 for c in categories},
            model=model,
            effort=effort,
            price_level=price,
            max_difficulty=1.0,
            min_confidence=0.0,
            review=review,
        )
        for category, model, effort, price, review in itertools.product(
            categories, models, r.efforts, r.price_levels, r.review
        )
    ]


class Router:
    def __init__(self, cfg: Config, options: list[Agent], solver: Solver, win_model: WinModel, rng: random.Random):
        self.cfg = cfg
        self.options = options
        self.solver = solver
        self.win_model = win_model
        self.rng = rng
        self.stats: dict[tuple[int, str, int], list[float]] = {}  # (option, category, band) -> [tries, wins]

    def band(self, task: Task) -> int:
        bands = self.cfg.router.difficulty_bands
        return min(bands - 1, int(task.difficulty * bands))

    def _sampled_success(self, option: Agent, task: Task) -> float:
        tries, wins = self.stats.get((option.id, task.category, self.band(task)), (0.0, 0.0))
        w, p0 = self.cfg.agent.prior_weight, self.cfg.agent.prior_success
        return self.rng.betavariate(wins + p0 * w, tries - wins + (1 - p0) * w)

    def learn(self, option: Agent, task: Task, success: bool) -> None:
        entry = self.stats.setdefault((option.id, task.category, self.band(task)), [0.0, 0.0])
        entry[0] += 1
        entry[1] += 1 if success else 0

    def choose(self, task: Task, wallet: Agent) -> tuple[Agent | None, float]:
        """The option with the best sampled expected profit, or None if none looks profitable."""
        best, best_value = None, 0.0
        for option in self.options:
            if option.genome.specialty != task.category:
                continue
            cost = self.solver.estimate_cost(option, task)
            if cost > wallet.balance:
                continue
            price = task.max_price * option.genome.price_level
            win = self.win_model.sample(client_score(option.reputation, price, task), self.rng)
            value = win * (self._sampled_success(option, task) * price - cost) - self.cfg.economy.bid_cost
            if value > best_value:
                best, best_value = option, value
        return best, best_value


def run_router_arm(
    cfg: Config,
    seed: int,
    market: Market,
    solver: Solver,
    models: list[str],
    *,
    log_attempts: bool = False,
    progress: Progress | None = None,
) -> ArmResult:
    from .experiment import ArmResult, attempt_record

    n = cfg.experiment.population_size
    categories = market.categories
    sandbox = Sandbox(cfg.sandbox)
    economy = Economy(sandbox, keep_ledger=cfg.experiment.save_ledger)
    population = Population()
    wallet = population.spawn(
        Genome({c: 1.0 / len(categories) for c in categories}, models[0]),
        reputation=cfg.economy.initial_reputation,
    )
    economy.fund(wallet, cfg.economy.initial_budget * n, 0)
    # Each option keeps its own reputation with clients, as each agent of a population does.
    options = [
        Agent(id=-(i + 1), genome=g, reputation=cfg.economy.initial_reputation)
        for i, g in enumerate(menu_genomes(cfg, categories, models))
    ]
    win_model = WinModel(cfg.agent.prior_win_rate, cfg.agent.prior_weight)
    router = Router(cfg, options, solver, win_model, random.Random(seed * 1000 + 4))
    rng = random.Random(seed * 1000 + 1)
    result = ArmResult("router", seed, initial_capital=economy.allocated)
    alpha = cfg.economy.reputation_alpha

    for generation in range(cfg.experiment.generations):
        tasks = market.tasks_for(generation)
        stats = RoundStats(offered=len(tasks))
        used: dict[str, int] = {}
        profit = 0.0
        worked = wallet.alive
        capacity = n * cfg.market.agent_capacity
        if worked:
            wallet.begin_generation()
            for task in tasks:
                option, _ = router.choose(task, wallet) if stats.assigned < capacity else (None, 0.0)
                if option is None:
                    stats.unbid += 1
                    stats.unserved.append((task.category, task.difficulty))
                    continue
                price = task.max_price * option.genome.price_level
                if cfg.economy.bid_cost > 0:
                    economy.charge(wallet, cfg.economy.bid_cost, "sales", generation, task.id)
                    stats.sales_cost += cfg.economy.bid_cost
                score = client_score(option.reputation, price, task)
                won = task.competitor_price is None or score >= client_score(
                    cfg.market.competitor_reputation, task.competitor_price, task
                )
                win_model.record(score, won)
                if not won:
                    stats.lost_to_competitors += 1
                    continue
                outcome = solver.attempt(option, task, rng)
                economy.charge(wallet, outcome.cost, "compute", generation, task.id)
                option.record_attempt(task.category, outcome.success, outcome.cost, alpha)
                router.learn(option, task, outcome.success)
                option.lifetime_cost += outcome.cost
                wallet.tasks_done += 1
                wallet.tasks_succeeded += 1 if outcome.success else 0
                if outcome.success:
                    economy.pay(wallet, price, generation, task.id)
                    option.lifetime_revenue += price
                    stats.succeeded += 1
                    stats.revenue += price
                stats.assigned += 1
                stats.compute_cost += outcome.cost
                used[option.genome.model] = used.get(option.genome.model, 0) + 1
                if log_attempts:
                    result.attempts.append(attempt_record("router", seed, task, option, price, outcome))
            economy.charge(wallet, cfg.economy.upkeep * n, "upkeep", generation)
            profit = wallet.end_generation()
            if wallet.balance <= 0:
                population.retire(wallet, generation, "bankrupt")
        working = n if worked else 0
        row = {
            "arm": "router",
            "seed": seed,
            "generation": generation,
            "population": working,
            "tasks_offered": stats.offered,
            "tasks_assigned": stats.assigned,
            "tasks_succeeded": stats.succeeded,
            "lost_to_competitors": stats.lost_to_competitors,
            "tasks_unbid": stats.unbid,
            "revenue": stats.revenue,
            "compute_cost": stats.compute_cost,
            "sales_cost": stats.sales_cost,
            "upkeep": cfg.economy.upkeep * n if working else 0.0,
            "net_profit": profit,
            "profit_per_agent": profit / n if working else 0.0,
            "success_rate": stats.succeeded / stats.assigned if stats.assigned else 0.0,
            "market_share": stats.assigned / stats.offered if stats.offered else 0.0,
            "mean_reputation": sum(o.reputation for o in options) / len(options),
            "spawn_fees": 0.0,
            "invested": 0.0,
            "treasury": economy.treasury,
            "wealth": economy.wealth(population.all()),
            "alive_after": n if wallet.alive else 0,
            "births": 0,
            "bankrupt": 0 if wallet.alive else int(wallet.died == generation),
            "defunded": 0,
            "outcompeted": 0,
        }
        total = sum(used.values())
        row.update({f"model:{m}": used.get(m, 0) / total if total else 0.0 for m in models})
        row.update({f"demand:{c}": w for c, w in market.demand.items()})
        result.rows.append(row)
        if progress is not None and log_attempts:
            progress(
                f"  gen {generation}: router, succeeded {stats.succeeded}/{stats.assigned}, "
                f"profit {profit:+.2f}, wealth {row['wealth']:.2f}"
            )

    from .experiment import _agent_record

    result.agents = [_agent_record(wallet, "router", seed)] + [
        _agent_record(o, "router", seed) for o in options if o.tasks_done
    ]
    result.ledger = [dict(arm="router", seed=seed, **t) for t in economy.ledger_rows()]
    return result
