# Research plan

What Astra Evolution is trying to find out, what is already known, and the
experiments that remain, each with the result that would count as an answer.

## Purpose

Astra Evolution is an open system in which a population of AI agents earns
money on tasks while paying for its own compute. Profitable agents pass their
strategies to children with small changes; unprofitable ones lose their
funding. A strategy is a set of decisions: which model to use, what to
specialize in, how much to think, whether to double-check, what to charge.
Selection runs only on measured profit.

The project has two goals:

1. **Research.** Answer the question: *can a population of AI agents, through
   selection and inheritance, learn to reliably earn more than it spends, and
   does it do better than simpler approaches?*
2. **Economic value.** Produce a tool and the numbers a real service can be
   built on: the cost of one accepted result, per model and per kind of task.

## Scope

In scope:

- the evolution engine: selection, inheritance, mutation, self-financed children;
- a simulated market for fast, exactly reproducible experiments;
- real models, local (Ollama) and paid (DeepSeek API), on tasks whose answers are checked automatically;
- owner mode: real tasks from a person, drafts by the agents, acceptance and payment recorded by that person;
- reports, charts and paired comparisons with control groups.

Out of scope, on purpose (see [safety.md](safety.md)):

- agents acting on the internet or contacting clients on their own;
- agents moving money; they only keep accounts, people pay and get paid;
- installing Astra on any machine except by its owner;
- paid API spending beyond a hard cap set by the owner.

## What is known so far

| Experiment | Result |
|---|---|
| Simulation, 10 seeds x 100 generations ([details](experiment.md)) | Evolution beats the same strategies left unchanged (9/10 seeds from a random start, 10/10 from a tuned start). From a random start it does not reach a strategy found offline by grid search (0/10). |
| Nine ablations | Letting agents of one population underbid each other costs about a fifth of the capital. The advantage holds in a stationary market. |
| Local models (qwen3.5:4b, Dolphin 8B), 1 seed | Evolving x1.26 vs. unchanged x1.02. Evolution dropped self-review and split work between the models. |
| Local models vs. DeepSeek API, 1 seed | Tie at x1.14. `deepseek-flash` solved 188 of 188 tasks at about $0.0002 each. Agents learning from their own experience captured most of the gain without selection. |
| Same, population refills after defunding, 5 seeds ([details](experiment.md#letting-the-population-refill-5-seeds)) | Evolution wins in 4 of 5 seeds (x1.17 vs. x1.03; revenue / full cost 1.70 vs. 1.11). It rescues a bad starting population and costs a little when the start is already good. Not yet statistically significant. |

## Remaining experiments

### Stage 2: real models (one to two weeks of mostly overnight runs, under $5 of API spend)

| # | Experiment | Question | Counts as "yes" |
|---|---|---|---|
| 4 | Refilling population, 5 seeds (**done: 4 of 5, criterion met**) | Does refilling after defunding let evolution beat the unchanged population on real models? | Wins in at least 4 of 5 seeds |
| 5 | A simple learning router (multi-armed bandit over models per task category) in place of evolution | Is evolution needed at all, or does a much simpler learner do as well? | Evolution beats the router in at least 9 of 10 seeds |
| 6 | Harder auto-checked tasks: code with unit tests, extraction from messy text, SQL | When no single model wins everything, does selection find better strategies? | Evolution beats both controls in at least 9 of 10 seeds |
| 7 | The best variant from 4-6, 10 seeds | Is the result statistically sound? | At least 9 of 10 paired wins (sign test p of about 0.01) |
| 8 | Task prices swept from low to high | At which price per task does a local model beat the API, and the reverse? | A break-even curve per task category |

### Stage 3: real money (one to two months, depends on finding paid work)

| # | Experiment | Question | Counts as "yes" |
|---|---|---|---|
| 9 | Owner mode, 30-50 real paid tasks in one niche, fixed best configuration | What does an accepted result really cost, and how often do clients accept? | Cost per accepted result clearly below its price; most results accepted |
| 10 | The same kind of tasks with evolution on | Does evolution improve real unit economics? | Lower cost per accepted result or higher acceptance than experiment 9 |

### Stage 4: only if stage 3 succeeds

A node that runs continuously on its owner's machine, and exchange of proven
strategies between nodes (see [roadmap.md](roadmap.md)).

## How results will be judged

- **Proven:** evolution beats both the unchanged population and the simple
  router in at least 9 of 10 paired runs.
- **Viable as a business:** on real tasks, the cost of an accepted result is
  well below its price and clients accept most results.
- **A clear "no" is also an answer.** If evolution turns out to be
  unnecessary, the useful product is the simpler part: measuring the cost of
  correct results and routing each task to the cheapest model that does it
  well.

## Main risk

Everything depends on stage 3: real clients with paid tasks. Without them the
project remains research. Stages 1 and 2 exist so that, when real work
arrives, the cost of each result and the configuration that delivers it are
already known.

## Contributing to the plan

Each experiment above is a good first contribution. Report the command, the
configuration and the result, including negative ones; see
[CONTRIBUTING.md](../CONTRIBUTING.md).
