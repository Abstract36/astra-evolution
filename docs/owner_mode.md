# Owner mode: real tasks, real money

Owner mode is how Astra meets real demand. You bring tasks people pay for;
a population of agents drafts the results on your machine with your local
models; you check the drafts, deliver the good ones yourself and record what
the client paid. Selection runs on those records, so over time the population
moves toward the models and working styles that earn you the most per unit of
compute.

Agents never contact clients, never send anything anywhere and never touch
money. Every draft is a file you read first.

## Setup

1. Install Ollama and at least one model, e.g. `ollama pull qwen2.5:7b`.
2. Edit [`config/owner.yaml`](../config/owner.yaml):
   - pick one money unit and use it everywhere;
   - set `ollama.cost_per_second` to what a second of generation really costs
     you (electricity plus hardware wear);
   - set `economy.initial_budget` and `sandbox.owner_budget`.
3. Create a workspace:

   ```bash
   astra init --workspace my-node --config config/owner.yaml
   ```

## The cycle

```bash
astra add-tasks --workspace my-node tasks/my_tasks.yaml   # new paid work
astra work      --workspace my-node                       # agents draft results
astra review    --workspace my-node                       # you accept or reject each draft
astra evolve    --workspace my-node                       # close the generation, run selection
astra status    --workspace my-node                       # population, money, tasks
```

`astra review` without a task id walks through every draft interactively. To
script it:

```bash
astra review --workspace my-node coffee-landing-01 --accept --paid 35
astra review --workspace my-node market-scan-01 --reject --reopen --note "too generic"
```

`--reopen` puts a rejected task back on the market for another agent.

## Task files

See [`tasks/example_tasks.yaml`](../tasks/example_tasks.yaml). Each task has an
id, a category, the brief, the price the client pays on acceptance, an optional
difficulty and an optional automatic check (`exact`, `contains` or `regex`).
A draft that fails its automatic check is rejected without asking you.

## What it is good for today

Local 4-14B models produce drafts, not finished work. Expect to edit. The value
is speed and the measurement: after a few generations the ledger shows which
models and settings produce accepted work at the lowest cost per accepted task,
category by category.

## Files

```
my-node/
  config.yaml     the configuration this workspace uses
  state.json      population, economy totals, generation, random state
  tasks.json      every task with its status, agent, cost and payment
  ledger.jsonl    append-only record of every money movement
  outbox/         one Markdown file per draft
```
