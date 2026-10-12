# The first experiment

## Question

> Can a population of AI agents, through selection, inheritance and mutation,
> learn to earn a sustainable net profit and pay for its own growth?

A first prototype has to show three things:

1. agents earn more than their **full** cost (compute, sales effort, upkeep and
   the cost of creating new agents);
2. evolution beats the **same strategies left unchanged**;
3. the population grows the capital it was given.

This experiment answers them in a simulated market, where thousands of
generations cost seconds and every number can be reproduced exactly. The
[Ollama experiment](#real-models-ollama) repeats the setup with real local
models.

## Setup

- **Market.** 120 tasks per generation in five categories (software
  development, data processing, automation, market research, digital products).
  Every task has a difficulty, a size and a client budget; harder tasks pay
  more. Demand per category drifts randomly, and an outside competitor bids on
  every task at 60-100% of the client budget.
- **Agents.** Each agent has a genome: specialization across categories, a
  model (small, medium or large), effort, price level, the hardest task it will
  take, the minimum confidence it needs to bid, and whether it reviews its own
  work. Agents learn from experience how often they succeed per category.
- **Economy.** 20 agents start with 100 credits each (2,000 in total). Every
  attempt costs compute; a successful one earns the agreed price. Making an
  offer costs 0.1, existing costs 1 per generation.
- **Selection.** Bankrupt agents leave. Agents that lose money four generations
  in a row lose their funding. When the population is full, the weakest 10% are
  replaced. Agents whose profit pays back a child within 15 generations create
  children from their own earnings, but only if the market left work unserved
  that the child could do.
- **Arms.** Four arms run on identical task streams for every seed:

| Arm | Start | Evolution |
|---|---|---|
| Evolving (random start) | 20 random strategies | yes |
| Static (random) | the same 20 random strategies | no |
| Static (hand-tuned) | the best fixed strategy from a 360-point grid search | no |
| Evolving (hand-tuned start) | the same grid-search strategy | yes |

The grid search ran on seeds 101-103; the evaluation uses seeds 1-10. In the
real world nobody has a perfect simulator of their market to grid-search on,
so *Static (hand-tuned)* is a deliberately strong, somewhat unfair opponent.

## Results

10 seeds x 100 generations. Full report: [results/first_evolution/report.md](results/first_evolution/report.md).

![Capital multiple by generation](results/first_evolution/capital.svg)

| Arm | Capital multiple | Profit per agent per generation (last quarter) | Revenue / full cost | Agents at end |
|---|---:|---:|---:|---:|
| Evolving (random start) | x1.45 ± 0.61 | +2.87 ± 2.12 | 1.22 ± 0.48 | 5.9 ± 2.7 |
| Static (random) | x0.25 ± 0.18 | -0.71 ± 0.21 | 0.45 ± 0.22 | 3.7 ± 2.3 |
| Static (hand-tuned) | x6.19 ± 1.05 | +4.77 ± 1.23 | 1.73 ± 0.07 | 16.7 ± 1.6 |
| Evolving (hand-tuned start) | **x8.46 ± 0.57** | **+7.96 ± 1.01** | **1.85 ± 0.07** | 19.3 ± 1.1 |

Paired by seed:

| Comparison | Wins | Capital multiple difference |
|---|---:|---:|
| Evolving vs Static, random start | 9/10 | +1.20 |
| Evolving vs Static, hand-tuned start | 10/10 | +2.27 |
| Evolving (random start) vs Static (hand-tuned) | 0/10 | -4.74 |

### Answers

1. **Yes, agents cover their full cost.** Revenue / full cost is 1.22 from a
   random start and 1.85 from the tuned start.
2. **Yes, evolution beats the same strategies left unchanged**, in 9/10 seeds
   from a random start (the tenth is a tie) and in 10/10 from the tuned start.
   Even the best strategy a grid search could find gets better. By the last
   generation, evolution had moved about a fifth of the agents to the cheaper
   model and kept the mix of specialists matched to demand as it drifted:
   automation rose to 35% of demand, and 35% of the evolved population's focus
   followed it, against 21% in the unchanging population (total distance
   between focus and demand 0.07 vs 0.18).
3. **Yes, capital grows** (x1.45 and x8.46), but from a random start it grows
   slowly, and the population stays small (about 6 of 20 slots). Self-financing
   is strict: an agent only gets a child once its own profit pays for one.

### What evolution does not do (yet)

From random strategies, 100 generations of evolution do **not** reach what an
offline grid search finds with a perfect simulator (0/10 seeds). Evolution
pays for its exploration with real money and only learns from the tasks it
actually gets. Whether it closes the gap with more generations, larger
populations or better operators is the next research question.

## Ablations

Same 10 seeds, one change at a time (`astra run --set ...`):

| Variant | Evolving (random) | Static (random) | Evolving (tuned) | Static (tuned) | Wins, random start | Wins, tuned start |
|---|---:|---:|---:|---:|---:|---:|
| default | x1.45 | x0.25 | x8.46 | x6.19 | 9/10 | 10/10 |
| `market.internal_competition=true` | x1.18 | x0.38 | x6.74 | x4.93 | 9/10 | 10/10 |
| `evolution.reinvest_returned=true` | x1.36 | x0.25 | x8.62 | x6.19 | 9/10 | 10/10 |
| `market.demand_drift=0` (stationary market) | x1.23 | x0.28 | x8.58 | x6.53 | 9/10 | 10/10 |
| demand shock at generation 50 (market research x6) | x1.39 | x0.25 | x8.07 | x5.80 | 9/10 | 10/10 |
| `evolution.crossover_rate=0` | x1.34 | x0.25 | x9.06 | x6.19 | 9/10 | 10/10 |
| `evolution.mutation_rate=0.6` | x1.32 | x0.25 | x8.26 | x6.19 | 9/10 | 9/10 |

- **Internal competition costs everyone about a fifth of the capital.** When
  agents of one population underbid each other, clients keep the margin.
- **The advantage does not rely on market drift.** In a stationary market
  evolution still improves the tuned strategy in 10/10 seeds; under a demand
  shock the unchanging strategy loses more.
- **Reinvesting money taken from losers changes little**, so the default is
  the stricter rule: children are paid for only from earnings.
- Crossover is not needed for this genome; a higher mutation rate hurts a
  little.

## Design lessons

Building the selection rules took several iterations. Each failure below is a
plausible way to design an "economic agent network", and each one broke it:

1. **Agents of one network must not underbid each other.** With every agent
   bidding separately, children with slightly lower prices took work from their
   parents and margins collapsed. The population now acts as one firm and
   offers each task once, through the agent with the best expected profit.
2. **Price on value, not on cost.** With cost-plus pricing an agent that found
   a cheaper model also had to charge less, so efficiency was not rewarded.
3. **Lost offers must cost something, and the network must learn what clients
   accept.** Otherwise the most expensive offer always looks best inside the
   network, and prices creep up until clients walk away. The population now
   shares a model of how often clients accept an offer at a given
   value-for-money score.
4. **Grow only into unserved demand that the child can actually serve.** A
   successful agent copied into an already saturated niche starves itself and
   its children. In a diagnostic run, one planted optimal agent was defunded
   by its own offspring until this rule was added.
5. **Do not defund everyone while everyone is still learning.** Early on all
   agents lose money; withdrawing funding from all losers at once wiped out the
   population. Losers are now defunded only while profitable agents exist.

## Real models (Ollama)

`astra ollama-run` repeats the setup with real local models on tasks that are
checked automatically (arithmetic, sorting, letter counting and e-mail
extraction). Agents choose among the installed models; the cost of an attempt
is the generation time actually measured, times `ollama.cost_per_second`.

A run on one consumer GPU (RTX 2070) with `qwen3.5:4b` and
`Dolphin3.0-Llama3.1-8B`: 10 agents, 10 generations, 20 tasks per generation
([report](results/ollama_evolution/report.md), every model answer in
[attempts.jsonl](results/ollama_evolution/attempts.jsonl)).

| Arm | Capital multiple | Revenue / full cost | Profit per agent per generation (last quarter) |
|---|---:|---:|---:|
| Evolving (random start) | x1.26 | 1.61 | +3.49 |
| Static (random) | x1.02 | 1.05 | -0.12 |

What the evolving population did with real models, comparing generations 0-4
with 5-9:

- **dropped self-review** (40% of agents to 0%): on these tasks a second pass
  doubled the compute bill without fixing enough answers;
- **divided the work by model**: Dolphin took arithmetic and e-mail
  extraction, where it is fast and mostly right, and qwen took counting and
  sorting;
- **cut compute spending from 59 to 37 credits while revenue rose from 92 to
  114**. The unchanged population went from 77 to 73 in revenue over the same
  generations.

It is one seed and ten generations, so read it as a working demonstration on
real models, not as statistical evidence.

A calibration run before it found that reasoning models (`deepseek-r1` 7B, 14B
and 70B) kept reasoning even with thinking disabled, used up every token and
solved none of the eight probe tasks, while costing 10-80 seconds per answer.
An evolving population drops such models quickly; a fixed configuration that
picked them would simply lose money.

## Limitations

- The simulated market is a model, and its parameters are guesses. The results
  show that the mechanism works under these assumptions, not that a real
  market behaves this way.
- Credits are virtual. Real money only enters through owner mode, where a human
  supplies tasks and records payments.
- Ten seeds give a clear sign but wide error bars for the random-start arms.

## Reproduce

```bash
astra run                                   # this experiment, about 6 seconds
astra run --seeds 30 --generations 300      # longer, more seeds
astra run --set market.internal_competition=true
astra ollama-run                            # real models (needs Ollama)
```

Runs are deterministic: the same configuration and seeds give the same numbers.
