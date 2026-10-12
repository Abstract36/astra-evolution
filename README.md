# Astra Evolution

**An evolving population of economic AI agents.** Agents spend a budget on
compute, earn revenue for the tasks they complete and are selected by net
profit. Profitable agents pay for children that inherit their strategy with
small mutations; persistently unprofitable ones lose their funding.

[![tests](https://github.com/Abstract36/astra-evolution/actions/workflows/tests.yml/badge.svg)](https://github.com/Abstract36/astra-evolution/actions/workflows/tests.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

> **Status: research prototype (v0.1).** Money is virtual in the experiments and
> recorded by a human in owner mode. Agents run in a sandbox: no network access
> beyond the local model server, no installation on other machines, no payments.

## The question

> Can a population of AI agents, through selection, inheritance and mutation,
> learn to earn a sustainable net profit and pay for its own growth?

A usual AI system gets a task from a person. Here, a population explores which
tasks it can do at a profit, how to do them (which model, how much compute,
whether to double-check, at what price) and which strategies deserve more
funding. Selection runs on measured results, not on anyone's opinion.

## First results

20 agents, 100 generations, 10 seeds, identical tasks for every arm
([full report](docs/results/first_evolution/report.md), [method and ablations](docs/experiment.md)):

![Capital multiple by generation](docs/results/first_evolution/capital.svg)

| Arm | Capital multiple | Revenue / full cost |
|---|---:|---:|
| Evolving, from a hand-tuned strategy | **x8.46** | **1.85** |
| Static, the same hand-tuned strategy | x6.19 | 1.73 |
| Evolving, from random strategies | x1.45 | 1.22 |
| Static, the same random strategies | x0.25 | 0.45 |

- **Evolution beats the same strategies left unchanged**: 10/10 seeds from the
  hand-tuned start (it was the best of a 360-point grid search) and 9/10 from a
  random start, the tenth a tie.
- **Evolving agents earn more than their full cost** (compute, sales, upkeep
  and the cost of their children) and grow their capital.
- **Not solved yet:** from random strategies, 100 generations do not reach what
  an offline grid search finds with a perfect simulator (0/10 seeds). That is
  the next research question.
- **With real models** (local Ollama models vs. DeepSeek's API, real token
  bills, one seed): `deepseek-flash` solved 188 of 188 tasks at about $0.0002
  each, and evolution matched but did not beat an unchanged population that
  simply learned from experience. The whole run cost $0.03 of real money.
  [Details](docs/experiment.md#local-models-vs-a-paid-api-deepseek).
- **Design lessons** that matter for any network of economic agents, for
  example that letting agents of one network underbid each other costs everyone
  about a fifth of the capital, are in [docs/experiment.md](docs/experiment.md#design-lessons).

## Quick start

Python 3.10+ is all you need for the simulation.

```bash
git clone https://github.com/Abstract36/astra-evolution
cd astra-evolution
pip install -e .

astra run                          # the first experiment, about 6 seconds
astra run --seeds 30 --generations 300
astra run --set market.internal_competition=true --set evolution.mutation_rate=0.5
```

Each run writes `results/<name>-<time>/` with `report.md`, `capital.svg`,
per-generation `generations.csv`, every agent with its lineage in
`agents.jsonl`, and `summary.json`. Same config and seeds give the same numbers.
Runs of different seeds, made one by one or on different machines, combine
with `astra merge --out results/all results/run-a results/run-b`.

Without installing: `pip install pyyaml && python experiments/first_evolution.py`.

### With real local models

Install [Ollama](https://ollama.com) and any small model, then:

```bash
ollama pull qwen2.5:3b
astra ollama-check                 # which models will be used
astra ollama-run                   # agents pick models and pay for measured GPU time
```

Tasks are checked automatically (arithmetic, sorting, counting, e-mail
extraction), and every model answer is saved to `attempts.jsonl`.

### Local models vs. a paid API

Let agents choose between your local models and DeepSeek's API, each billed
at what it really costs (GPU seconds locally, tokens on the API), with a hard
cap on real spending:

```bash
export DEEPSEEK_API_KEY=sk-...                 # read from the environment only
astra check   --config config/deepseek.yaml    # each model answers 2 + 2 and shows its cost
astra llm-run --config config/deepseek.yaml    # spending cap: sandbox.max_api_spend_usd ($1)
```

Any OpenAI-compatible API works: set `api.base_url`, the models and their
prices, and add the host to `sandbox.allowed_hosts`.

### Owner mode: real tasks, real payments

You bring tasks people pay for; agents draft results locally; you review,
deliver and record what the client paid. Selection runs on those records.

```bash
astra init --workspace my-node --config config/owner.yaml
astra add-tasks --workspace my-node tasks/example_tasks.yaml
astra work --workspace my-node
astra review --workspace my-node
astra evolve --workspace my-node
```

See [docs/owner_mode.md](docs/owner_mode.md).

## How it works

Each agent has a **genome**: specialization across task categories, a model,
effort, price level, the hardest task it accepts, the confidence it needs to
bid, and whether it reviews its own work. It also has **memory** (its success
rate per category) and a **reputation** with clients.

Every generation:

1. Clients post tasks. The population offers each task once, through the agent
   with the highest expected profit; the client compares it with an outside
   competitor on value for money.
2. The winner does the task, pays for compute and is paid if it succeeds.
3. Agents pay upkeep. Their operating profit is their fitness.
4. Selection: bankrupt agents leave; persistent losers lose their funding; when
   the population is full, the weakest are replaced; agents whose profit repays
   a child in time create one from their own earnings, if the market left work
   the child could do.

Details: [docs/architecture.md](docs/architecture.md).

## Safety

- Children are created only within the budget and population limit set by the owner.
- Nothing is ever installed on another device; a node exists because its owner started it.
- Network access is limited to hosts the owner allows (the local machine by default).
- Agents never move money; in owner mode a human records every payment.

See [docs/safety.md](docs/safety.md).

## Research plan

What is known, what remains and what result would count as an answer for each
remaining experiment: [docs/research_plan.md](docs/research_plan.md).

## Roadmap

1. **Evolution Engine**: selection of strategies by measurable results (this release).
2. **Local Agent Runtime**: Astra running continuously on a participant's own computer, on tasks they choose.
3. **Astra Network**: a voluntary network of nodes that exchange strategies and verified results.

See [docs/roadmap.md](docs/roadmap.md).

## Project layout

```
astra/            the package (agent, population, evolution, economy, market, sandbox, ...)
config/           default.yaml (first experiment), ollama.yaml, owner.yaml
experiments/      runnable scripts for the experiments
tasks/            example task file for owner mode
docs/             architecture, experiment write-up, safety, roadmap, published results
tests/            pytest suite (about a second)
```

## Contributing

Experiments, negative results included, are the most valuable contribution.
See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT, see [LICENSE](LICENSE).
