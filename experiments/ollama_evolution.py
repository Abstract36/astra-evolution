"""The same experiment with real local models served by Ollama.

Agents choose among the models you have installed, answer automatically
checked micro-tasks and pay for the compute time they actually use.

    ollama pull qwen2.5:3b                    # any small model works
    python experiments/ollama_evolution.py
    python experiments/ollama_evolution.py --generations 20

Equivalent to ``astra ollama-run --config config/ollama.yaml``. Every model
answer is saved to attempts.jsonl next to the report.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from astra.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["ollama-run", "--config", str(ROOT / "config" / "ollama.yaml"), *sys.argv[1:]]))
