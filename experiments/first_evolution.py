"""First experiment: 20 agents with virtual budgets, evolution vs. unchanging controls.

Run from the repository root (no installation needed):

    python experiments/first_evolution.py
    python experiments/first_evolution.py --generations 200 --seeds 20
    python experiments/first_evolution.py --set market.demand_drift=0.3

Equivalent to ``astra run --config config/default.yaml``. Results go to
results/first_evolution-<timestamp>/ (report.md, capital.svg, CSV and JSON).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from astra.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["run", "--config", str(ROOT / "config" / "default.yaml"), *sys.argv[1:]]))
