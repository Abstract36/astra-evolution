# Architecture

```
astra/
  config.py         typed configuration, YAML loading, --set overrides, validation
  agent.py          Genome (heritable strategy), Memory (learned experience), Agent, bidding
  population.py     every agent that ever lived, lineage, average-strategy statistics
  market.py         Task, simulated market with drifting demand, auction, client acceptance model
  solvers.py        SimulatedSolver (fast model of quality/cost), LLMSolver (real models via Ollama)
  economy.py        owner funding, costs, revenue, transfers, treasury, accounting identity
  evolution.py      bankruptcy, defunding, replacement, reproduction, mutation, crossover
  sandbox.py        hard limits set by the owner: population, spawns, budget, network hosts, tokens
  ollama_client.py  minimal Ollama HTTP client (standard library only)
  api_client.py     OpenAI-compatible paid API client (DeepSeek) with a hard spending cap; model router
  verifiable.py     auto-checkable micro-tasks for real models
  experiment.py     runs arms x seeds on identical task streams
  results.py        summary statistics, Markdown report, SVG chart, CSV/JSONL output
  owner.py          owner mode: real tasks, local drafting, human review, persistent workspace
  cli.py            the `astra` command
```

## One generation

```
market.tasks_for(g)                      tasks with category, difficulty, size, client budget
   |
   v
trade_round                              for every task:
   |  each agent with free capacity        Agent.decide_bid -> Bid | None
   |  population picks one offer           highest expected profit
   |  client compares with outsider        value for money = (reputation + 0.25) * budget / price
   |  winner attempts the task             solver.attempt -> success, measured cost
   |  money moves                          compute cost, sales cost, revenue on success
   v
upkeep charged, Agent.end_generation()   operating profit appended to the agent's history
   |
   v
EvolutionEngine.step                     bankrupt -> defunded -> outcompeted -> children
```

## Genome

| Gene | Range | Meaning |
|---|---|---|
| `focus` | weights summing to 1 | specialization across task categories |
| `model` | one of the models | which model does the work |
| `effort` | 0.5-2.0 | compute multiplier: costs more, raises quality (real models: step-by-step reasoning and a larger output budget; on the API, effort >= 1 turns thinking on, >= 1.6 at high effort) |
| `price_level` | 0.3-1.0 | price as a share of the client's budget |
| `max_difficulty` | 0.1-1.0 | hardest task the agent will take |
| `min_confidence` | 0.05-0.85 | lowest estimated success rate at which it still bids |
| `review` | yes/no | second pass that checks and fixes the first answer |

Children get a mutated copy: each continuous gene changes with probability
`mutation_rate` by Gaussian noise of `mutation_scale` times its range; focus
weights are perturbed log-normally and occasionally jump to a new niche; the
model moves to a neighbouring one; review flips rarely. With probability
`crossover_rate` the child mixes the genes of two parents first.

Children also inherit a discounted copy of the parent's memory
(`memory_inheritance`) and part of its reputation
(`reputation_inheritance`).

## Bidding

An agent bids when the task is within its specialization and risk appetite, it
can afford the compute, and

```
expected profit = P(client accepts) x (P(success) x price - cost) - bid cost  >  0
```

`P(success)` is the agent's own success rate in that category (a Beta
posterior starting from `agent.prior_success`); `P(client accepts)` is learned
by the whole population from every offer it made, as a function of the
offer's value-for-money score (`WinModel`). During its first
`exploration_trials` attempts in a category an agent bids regardless of its
confidence, so that it can learn.

The population offers each task once, through the bid with the highest
expected profit. `market.internal_competition: true` instead lets every agent
bid and the client choose; see the ablations in [experiment.md](experiment.md).

## Simulated solver

```
capability = quality(model) * (0.35 + 0.65 * sqrt(focus[category])) + 0.12 * ln(effort) + 0.06 * review
P(success) = sigmoid(success_sharpness * (capability - difficulty))
cost       = size * cost_per_unit(model) * effort * (1 + review_cost_overhead * review) * noise
```

Specialists beat generalists in their own category; big models are better but
expensive; effort has diminishing returns.

## Money

All amounts are credits. `Economy` keeps the accounting identity

```
wealth = allocated + revenue - compute - sales - upkeep - spawn fees
```

where wealth is the sum of all balances plus the treasury. The tests check it
every generation for every arm. Operating profit (revenue minus compute, sales
and upkeep) is an agent's fitness; spawn fees and endowments are investments
and do not count against it.

## Selection

See the module docstring of [`astra/evolution.py`](../astra/evolution.py) for
the exact rules. In short: money running out is final for everyone; with
evolution on, persistent losers lose their funding, the weakest are replaced
when the population is full, and profitable agents pay for children only when
there is unserved work their children could do.

## Extending

- **A new task source**: anything with `categories`, `demand` and
  `tasks_for(generation) -> list[Task]` works as a market.
- **A new way to do the work**: implement `estimate_cost(agent, task)` and
  `attempt(agent, task, rng) -> Outcome` (see `solvers.Solver`).
- **New genes**: add them to `Genome` and `GENE_BOUNDS`, and use them in a
  solver or in `Agent.decide_bid`.

## Determinism

Every random choice comes from `random.Random` instances seeded from the
experiment seed: one for the market (shared by all arms of a seed, so they see
identical tasks), one for outcomes, one for evolution and one for the initial
genomes.
