# Astra Evolution: ollama_evolution

1 seed(s) x 10 generations, 10 agents per arm at the start. Generated 2026-10-12 12:00 UTC.
Every arm of a seed sees exactly the same tasks. Values are mean ± standard deviation over seeds.

## Verdict

- **Do evolving agents earn more than their full cost (compute + sales + upkeep + spawning)?** Yes: revenue / full cost = Evolving (random start) 1.61.
- **Does evolution improve on the same strategies kept unchanged?** Yes (one seed: a demonstration, not evidence): Evolving (random start) vs Static (random): wins in 1/1 seeds, capital multiple +0.24.
- **Does the evolving population grow its capital?** Yes: Evolving (random start) x1.26 after 10 generations.

## Results by arm

| Arm | Capital multiple | Operating profit | Profit per agent per gen (last quarter) | Success rate | Market share | Revenue / full cost | Agents at end |
|---|---:|---:|---:|---:|---:|---:|---:|
| Evolving (random start) | x1.26 | +79.3 | +3.49 | 62% | 59% | 1.61 | 4.0 |
| Static (random) | x1.02 | +6.5 | -0.12 | 56% | 50% | 1.05 | 10.0 |

## Paired comparisons

Same seed, same tasks; a win means a higher final capital.

| Arm | Baseline | Wins | Capital multiple difference | Profit per agent difference (last quarter) |
|---|---|---:|---:|---:|
| Evolving (random start) | Static (random) | 1/1 | +0.24 (min +0.24, max +0.24) | +3.62 |

## Capital over time

![Capital multiple by generation](capital.svg)

| Generation | Evolving (random start) | Static (random) |
|---:|---:|---:|
| 0 | x0.96 | x0.97 |
| 1 | x0.96 | x0.96 |
| 2 | x0.96 | x0.97 |
| 3 | x0.98 | x0.96 |
| 4 | x1.04 | x0.96 |
| 5 | x1.10 | x0.98 |
| 6 | x1.13 | x1.00 |
| 7 | x1.17 | x1.03 |
| 8 | x1.20 | x1.02 |
| 9 | x1.26 | x1.02 |

## What evolution selected: Evolving (random start)

Average strategy of working agents in the first and the last generation.

| Trait | First generation | Last generation |
|---|---:|---:|
| gene:effort | 1.31 | 0.98 |
| gene:price_level | 0.71 | 0.91 |
| gene:max_difficulty | 0.58 | 0.62 |
| gene:min_confidence | 0.49 | 0.31 |
| gene:review | 0.40 | 0.00 |
| specialization | 0.58 | 0.64 |
| model:qwen3.5:4b | 0.30 | 0.50 |
| model:hf.co/cognitivecomputations/Dolphin3.0-Llama3.1-8B-GGUF:Q4_0 | 0.70 | 0.50 |
| focus:arithmetic | 0.12 | 0.12 |
| focus:sorting | 0.32 | 0.12 |
| focus:counting | 0.30 | 0.58 |
| focus:extraction | 0.26 | 0.18 |

Market demand in the last generation, to compare with `focus:*` above: arithmetic 25%, sorting 25%, counting 25%, extraction 25%.

## How to read this

- **Capital multiple**: (all agent balances, debts of bankrupt agents included, + money taken back from defunded agents) / initial funding. Above 1 means the population earned more than it spent.
- **Operating profit**: revenue minus compute, sales and upkeep costs, summed over all agents and generations.
- **Revenue / full cost**: revenue divided by compute + sales + upkeep + spawn fees.
- **Static** arms never reproduce or mutate; agents only leave them by going bankrupt.
- Beating *Static (random)* is easy. Beating *Static (hand-tuned)* is the meaningful test.
