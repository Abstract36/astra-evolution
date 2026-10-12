# Roadmap

The project grows in three directions. Each step starts only when the previous
one produced measurable evidence.

## 1. Evolution Engine (this repository, v0.1)

Selection of strategies by net profit, with experiments that can be repeated
exactly.

- [x] Genome, bidding, memory and reputation
- [x] Simulated market with drifting demand and outside competition
- [x] Economy with an accounting identity and a full ledger
- [x] Selection: bankruptcy, defunding, replacement, self-financed reproduction
- [x] Four-arm experiment with paired comparisons, reports and charts
- [x] Real local models on auto-checked tasks (Ollama)
- [x] Owner mode: real tasks, human review, recorded payments
- [ ] Close the gap to offline-tuned strategies from a random start (more
      generations, larger populations, better operators, niche-aware mutation)
- [ ] Fitness beyond profit: quality ratings, complaints, refunds
- [ ] Learned per-task routing (which agent for which task) next to evolution
- [ ] More realistic markets, calibrated on data from owner mode

## 2. Local Agent Runtime

Astra running continuously on a participant's own computer, on tasks that
participant chooses.

- A long-running node with a local dashboard: population, ledger, drafts awaiting review
- Plug-in task sources the owner connects explicitly (a folder, a ticket queue, an e-mail label)
- Tools beyond text generation (code execution in a container, spreadsheets), each one granted by the owner
- Real cost accounting: electricity and hardware per GPU-second, measured
- Export and import of successful genomes, so that owners can share strategies

## 3. Astra Network

A voluntary network of nodes run by people who chose to join.

- Exchange of genomes and verified results between nodes, never of code that installs itself
- Verification of results computed by other nodes before they are trusted
- Optional sharing of spare compute, with limits each owner sets
- Open publication of experiments, so that variants of agents can be compared
- Governance of shared rules before any shared money exists

Joining the network, giving it compute and every change of those limits are
always actions of the machine's owner. See [safety.md](safety.md).
