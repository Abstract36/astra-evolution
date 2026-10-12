# Astra Evolution: first_evolution

10 seed(s) x 100 generations, 20 agents per arm at the start. Generated 2026-10-12 11:58 UTC.
Every arm of a seed sees exactly the same tasks. Values are mean ± standard deviation over seeds.

## Verdict

- **Do evolving agents earn more than their full cost (compute + sales + upkeep + spawning)?** Yes: revenue / full cost = Evolving (random start) 1.22, Evolving (hand-tuned start) 1.85.
- **Does evolution improve on the same strategies kept unchanged?** Yes: Evolving (random start) beats Static (random) in 9/10 seeds (capital multiple +1.20); Evolving (hand-tuned start) beats Static (hand-tuned) in 10/10 seeds (capital multiple +2.27).
- **Does evolution from a random start match a strategy tuned offline by grid search?** No: wins in 0/10 seeds (capital multiple -4.74).
- **Does the evolving population grow its capital?** Yes: Evolving (random start) x1.45, Evolving (hand-tuned start) x8.46 after 100 generations.

## Results by arm

| Arm | Capital multiple | Operating profit | Profit per agent per gen (last quarter) | Success rate | Market share | Revenue / full cost | Agents at end |
|---|---:|---:|---:|---:|---:|---:|---:|
| Evolving (random start) | x1.45 ± 0.61 | +978.3 ± 1261.2 | +2.87 ± 2.12 | 78% ± 13% | 15% ± 7% | 1.22 ± 0.48 | 5.9 ± 2.7 |
| Static (random) | x0.25 ± 0.18 | -1502.7 ± 356.0 | -0.71 ± 0.21 | 77% ± 12% | 5% ± 3% | 0.45 ± 0.22 | 3.7 ± 2.3 |
| Static (hand-tuned) | x6.19 ± 1.05 | +10381.5 ± 2099.4 | +4.77 ± 1.23 | 90% ± 1% | 48% ± 7% | 1.73 ± 0.07 | 16.7 ± 1.6 |
| Evolving (hand-tuned start) | x8.46 ± 0.57 | +15389.6 ± 1202.4 | +7.96 ± 1.01 | 88% ± 1% | 64% ± 4% | 1.85 ± 0.07 | 19.3 ± 1.1 |

## Paired comparisons

Same seed, same tasks; a win means a higher final capital.

| Arm | Baseline | Wins | Capital multiple difference | Profit per agent difference (last quarter) |
|---|---|---:|---:|---:|
| Evolving (random start) | Static (random) | 9/10 | +1.20 (min +0.00, max +2.05) | +3.58 |
| Evolving (random start) | Static (hand-tuned) | 0/10 | -4.74 (min -5.79, max -2.10) | -1.90 |
| Evolving (hand-tuned start) | Static (hand-tuned) | 10/10 | +2.27 (min +0.11, max +3.86) | +3.20 |

## Capital over time

![Capital multiple by generation](capital.svg)

| Generation | Evolving (random start) | Static (random) | Static (hand-tuned) | Evolving (hand-tuned start) |
|---:|---:|---:|---:|---:|
| 0 | x0.98 | x0.98 | x1.03 | x1.03 |
| 10 | x0.95 | x0.86 | x1.69 | x1.72 |
| 20 | x0.98 | x0.76 | x2.34 | x2.49 |
| 30 | x1.02 | x0.66 | x2.95 | x3.24 |
| 40 | x1.06 | x0.58 | x3.50 | x4.00 |
| 50 | x1.11 | x0.51 | x4.02 | x4.77 |
| 60 | x1.16 | x0.45 | x4.48 | x5.52 |
| 70 | x1.22 | x0.39 | x4.94 | x6.28 |
| 80 | x1.29 | x0.33 | x5.39 | x7.05 |
| 90 | x1.37 | x0.28 | x5.83 | x7.79 |
| 99 | x1.45 | x0.25 | x6.19 | x8.46 |

## What evolution selected: Evolving (random start)

Average strategy of working agents in the first and the last generation.

| Trait | First generation | Last generation |
|---|---:|---:|
| gene:effort | 1.24 | 1.14 |
| gene:price_level | 0.64 | 0.64 |
| gene:max_difficulty | 0.54 | 0.38 |
| gene:min_confidence | 0.49 | 0.40 |
| gene:review | 0.47 | 0.43 |
| specialization | 0.50 | 0.51 |
| model:small | 0.35 | 0.83 |
| model:medium | 0.35 | 0.12 |
| model:large | 0.30 | 0.06 |
| focus:software_dev | 0.19 | 0.11 |
| focus:data_processing | 0.21 | 0.25 |
| focus:automation | 0.23 | 0.30 |
| focus:market_research | 0.19 | 0.22 |
| focus:digital_products | 0.19 | 0.12 |

Market demand in the last generation, to compare with `focus:*` above: software_dev 19%, data_processing 19%, automation 35%, market_research 13%, digital_products 13%.

## What evolution selected: Evolving (hand-tuned start)

Average strategy of working agents in the first and the last generation.

| Trait | First generation | Last generation |
|---|---:|---:|
| gene:effort | 0.75 | 0.69 |
| gene:price_level | 0.80 | 0.80 |
| gene:max_difficulty | 0.65 | 0.62 |
| gene:min_confidence | 0.45 | 0.47 |
| gene:review | 0.00 | 0.14 |
| specialization | 1.00 | 0.99 |
| model:small | 0.00 | 0.18 |
| model:medium | 1.00 | 0.81 |
| model:large | 0.00 | 0.01 |
| focus:software_dev | 0.30 | 0.13 |
| focus:data_processing | 0.25 | 0.25 |
| focus:automation | 0.20 | 0.35 |
| focus:market_research | 0.15 | 0.15 |
| focus:digital_products | 0.10 | 0.13 |

Market demand in the last generation, to compare with `focus:*` above: software_dev 19%, data_processing 19%, automation 35%, market_research 13%, digital_products 13%.

## How to read this

- **Capital multiple**: (all agent balances, debts of bankrupt agents included, + money taken back from defunded agents) / initial funding. Above 1 means the population earned more than it spent.
- **Operating profit**: revenue minus compute, sales and upkeep costs, summed over all agents and generations.
- **Revenue / full cost**: revenue divided by compute + sales + upkeep + spawn fees.
- **Static** arms never reproduce or mutate; agents only leave them by going bankrupt.
- Beating *Static (random)* is easy. Beating *Static (hand-tuned)* is the meaningful test.
