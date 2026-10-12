# Safety and consent

Astra studies agents that earn money and create copies of themselves. That is
exactly the kind of system that must stay under the control of the people
whose money and machines it uses. These rules are part of the design, not
promises on top of it.

## Rules

1. **Children only within the owner's budget and space.** Agents create
   children from money they earned, inside the population limit and the spawn
   limit set by the owner (`sandbox.max_population`,
   `sandbox.max_spawns_per_generation`). The owner's total funding is capped by
   `sandbox.owner_budget`.
2. **No installation on any device without its owner's consent.** This version
   contains no code that copies, installs or starts Astra anywhere else. A node
   exists only because the owner of that machine installed and started it.
   Future network features will keep this property: joining is an action of
   the machine's owner, never of an agent.
3. **No uncontrolled network access.** The only network client is the local
   Ollama client, and every URL is checked against `sandbox.allowed_hosts`
   (local machine only by default). Agents cannot browse, call APIs or contact
   people.
4. **No autonomous money movement.** Simulated credits never leave the
   process. In owner mode, agents draft results; the owner decides what to
   deliver and records what was actually paid. Agents have no payment
   credentials and no way to use any.
5. **Everything is recorded.** Every money movement goes to a ledger, every
   model answer of the real-model experiment is saved, and every drafted result
   in owner mode is a file the owner can read before anything happens.

## Where the limits are enforced

| Limit | Enforced in |
|---|---|
| population size, spawns per generation | `Sandbox.check_population`, `Sandbox.check_spawn` (called by `EvolutionEngine` before every birth) |
| owner budget | `Sandbox.check_allocation` (called by `Economy.fund`) |
| network hosts | `Sandbox.check_url` (called when an `OllamaClient` is created) |
| output length per model call | `Sandbox.clamp_tokens` |
| request time | `sandbox.request_timeout` |

Tests in `tests/test_sandbox.py` and `tests/test_evolution.py` check these.

## Optimizing for profit

Selecting for net profit rewards whatever earns money, including things that
should not. In this version agents cannot act outside their sandbox, so the
risk is limited to bad drafts. Before agents ever act in the world on their
own, fitness has to include more than profit: quality judged by people,
complaints, refunds and hard rules that no profit can outweigh. See the
[roadmap](roadmap.md).

## Reporting a problem

If you find a way around any of these limits, please open an issue marked
`security`, or contact the maintainers privately if it could be misused.
