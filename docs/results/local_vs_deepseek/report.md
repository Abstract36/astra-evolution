# Astra Evolution: local_vs_deepseek

1 seed(s) x 12 generations, 12 agents per arm at the start. Generated 2026-10-12 12:30 UTC.
Every arm of a seed sees exactly the same tasks. Values are mean ± standard deviation over seeds.

## Verdict

- **Do evolving agents earn more than their full cost (compute + sales + upkeep + spawning)?** Yes: revenue / full cost = Evolving (random start) 1.64.
- **Does evolution improve on the same strategies kept unchanged?** No clear difference (one seed: a demonstration, not evidence): Evolving (random start) vs Static (random): wins in 1/1 seeds, capital multiple +0.00.
- **Does the evolving population grow its capital?** Yes: Evolving (random start) x1.14 after 12 generations.

Paid API: 188 calls, $0.0331 of real money (priced from the token usage the API reported).

## Results by arm

| Arm | Capital multiple | Operating profit | Profit per agent per gen (last quarter) | Success rate | Market share | Revenue / full cost | Agents at end |
|---|---:|---:|---:|---:|---:|---:|---:|
| Evolving (random start) | x1.14 | +36.0 | +0.47 | 71% | 67% | 1.64 | 6.0 |
| Static (random) | x1.14 | +33.4 | +0.22 | 67% | 73% | 1.57 | 12.0 |

## Paired comparisons

Same seed, same tasks; a win means a higher final capital.

| Arm | Baseline | Wins | Capital multiple difference | Profit per agent difference (last quarter) |
|---|---|---:|---:|---:|
| Evolving (random start) | Static (random) | 1/1 | +0.00 (min +0.00, max +0.00) | +0.25 |

## Capital over time

![Capital multiple by generation](capital.svg)

| Generation | Evolving (random start) | Static (random) |
|---:|---:|---:|
| 0 | x1.00 | x0.99 |
| 1 | x1.00 | x1.00 |
| 2 | x1.01 | x1.01 |
| 3 | x1.03 | x1.03 |
| 4 | x1.05 | x1.05 |
| 5 | x1.06 | x1.06 |
| 6 | x1.08 | x1.08 |
| 7 | x1.09 | x1.10 |
| 8 | x1.10 | x1.11 |
| 9 | x1.12 | x1.11 |
| 10 | x1.13 | x1.12 |
| 11 | x1.14 | x1.14 |

## What evolution selected: Evolving (random start)

Average strategy of working agents in the first and the last generation.

| Trait | First generation | Last generation |
|---|---:|---:|
| gene:effort | 1.30 | 1.33 |
| gene:price_level | 0.71 | 0.71 |
| gene:max_difficulty | 0.59 | 0.73 |
| gene:min_confidence | 0.46 | 0.44 |
| gene:review | 0.33 | 0.33 |
| specialization | 0.56 | 0.47 |
| model:qwen3.5:4b | 0.00 | 0.00 |
| model:hf.co/cognitivecomputations/Dolphin3.0-Llama3.1-8B-GGUF:Q4_0 | 0.33 | 0.67 |
| model:deepseek-flash | 0.58 | 0.33 |
| model:deepseek-v4-pro | 0.08 | 0.00 |
| focus:arithmetic | 0.14 | 0.26 |
| focus:sorting | 0.34 | 0.33 |
| focus:counting | 0.27 | 0.20 |
| focus:extraction | 0.26 | 0.22 |

Market demand in the last generation, to compare with `focus:*` above: arithmetic 25%, sorting 25%, counting 25%, extraction 25%.

## How to read this

- **Capital multiple**: (all agent balances, debts of bankrupt agents included, + money taken back from defunded agents) / initial funding. Above 1 means the population earned more than it spent.
- **Operating profit**: revenue minus compute, sales and upkeep costs, summed over all agents and generations.
- **Revenue / full cost**: revenue divided by compute + sales + upkeep + spawn fees.
- **Static** arms never reproduce or mutate; agents only leave them by going bankrupt.
- Beating *Static (random)* is easy. Beating *Static (hand-tuned)* is the meaningful test.
