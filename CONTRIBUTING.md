# Contributing

Thanks for your interest. Astra is a research project: the most valuable
contributions are experiments that change what we know, and code that makes
them easier to run and trust.

## Setup

```bash
git clone https://github.com/Abstract36/astra-evolution
cd astra-evolution
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Ground rules

- **Results must be reproducible.** Every random choice goes through a seeded
  `random.Random`. If you report a result, include the command and config.
- **Report what you found, including negative results.** If evolution loses to
  a baseline under some setting, that is worth a pull request too.
- **Keep the accounting identity.** Any new money flow goes through `Economy`
  and keeps `tests/test_experiment.py::test_money_is_conserved` green.
- **Never weaken the sandbox.** No code that installs or starts Astra on other
  machines, contacts hosts outside `sandbox.allowed_hosts` or moves real money.
  See [docs/safety.md](docs/safety.md).
- **Add tests** for new behaviour. The suite runs in about a second; keep it that way.

## Good first contributions

- New auto-checkable task generators in `astra/verifiable.py`
- New ablations, written up like the ones in [docs/experiment.md](docs/experiment.md)
- A market calibrated on real data from owner mode
- Better mutation operators for `focus` (niche-aware mutation)

## Sharing experiment results

Put the generated `report.md`, `summary.json` and `capital.svg` under
`docs/results/<name>/` and describe the setup and what you learned in the pull
request.
