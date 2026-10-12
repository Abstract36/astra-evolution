# Astra Evolution: local_vs_deepseek

5 seed(s) x 12 generations, 12 agents per arm at the start. Generated 2026-10-12 14:19 UTC.
Every arm of a seed sees exactly the same tasks. Values are mean ± standard deviation over seeds.

## Verdict

- **Do evolving agents earn more than their full cost (compute + sales + upkeep + spawning)?** Yes: revenue / full cost = Evolving (random start) 1.70.
- **Does evolution improve on the same strategies kept unchanged?** Yes: Evolving (random start) vs Static (random): wins in 4/5 seeds, capital multiple +0.14.
- **Does the evolving population grow its capital?** Yes: Evolving (random start) x1.17 after 12 generations.

Paid API: 761 calls, $0.1113 of real money (priced from the token usage the API reported).

## Results by arm

| Arm | Capital multiple | Operating profit | Profit per agent per gen (last quarter) | Success rate | Market share | Revenue / full cost | Agents at end |
|---|---:|---:|---:|---:|---:|---:|---:|
| Evolving (random start) | x1.17 ± 0.14 | +45.7 ± 31.8 | +0.68 ± 0.45 | 67% ± 8% | 68% ± 10% | 1.70 ± 0.61 | 9.2 ± 3.0 |
| Static (random) | x1.03 ± 0.10 | +6.9 ± 23.0 | +0.07 ± 0.16 | 64% ± 7% | 50% ± 14% | 1.11 ± 0.47 | 12.0 ± 0.0 |

## Paired comparisons

Same seed, same tasks; a win means a higher final capital.

| Arm | Baseline | Wins | Capital multiple difference | Profit per agent difference (last quarter) |
|---|---|---:|---:|---:|
| Evolving (random start) | Static (random) | 4/5 | +0.14 (min -0.04, max +0.40) | +0.61 |

## Capital over time

![Capital multiple by generation](capital.svg)

| Generation | Evolving (random start) | Static (random) |
|---:|---:|---:|
| 0 | x0.99 | x1.00 |
| 1 | x0.99 | x1.00 |
| 2 | x1.00 | x0.99 |
| 3 | x1.01 | x1.00 |
| 4 | x1.03 | x1.00 |
| 5 | x1.04 | x1.01 |
| 6 | x1.06 | x1.01 |
| 7 | x1.08 | x1.01 |
| 8 | x1.10 | x1.02 |
| 9 | x1.12 | x1.02 |
| 10 | x1.14 | x1.02 |
| 11 | x1.17 | x1.03 |

## What evolution selected: Evolving (random start)

Average strategy of working agents in the first and the last generation.

| Trait | First generation | Last generation |
|---|---:|---:|
| gene:effort | 1.26 | 1.19 |
| gene:price_level | 0.68 | 0.81 |
| gene:max_difficulty | 0.59 | 0.85 |
| gene:min_confidence | 0.47 | 0.50 |
| gene:review | 0.45 | 0.36 |
| specialization | 0.57 | 0.50 |
| model:qwen3.5:4b | 0.25 | 0.03 |
| model:hf.co/cognitivecomputations/Dolphin3.0-Llama3.1-8B-GGUF:Q4_0 | 0.33 | 0.56 |
| model:deepseek-flash | 0.28 | 0.39 |
| model:deepseek-v4-pro | 0.13 | 0.02 |
| focus:arithmetic | 0.25 | 0.24 |
| focus:sorting | 0.25 | 0.21 |
| focus:counting | 0.24 | 0.24 |
| focus:extraction | 0.27 | 0.32 |

Market demand in the last generation, to compare with `focus:*` above: arithmetic 25%, sorting 25%, counting 25%, extraction 25%.

## How to read this

- **Capital multiple**: (all agent balances, debts of bankrupt agents included, + money taken back from defunded agents) / initial funding. Above 1 means the population earned more than it spent.
- **Operating profit**: revenue minus compute, sales and upkeep costs, summed over all agents and generations.
- **Revenue / full cost**: revenue divided by compute + sales + upkeep + spawn fees.
- **Static** arms never reproduce or mutate; agents only leave them by going bankrupt.
- Beating *Static (random)* is easy. Beating *Static (hand-tuned)* is the meaningful test.
