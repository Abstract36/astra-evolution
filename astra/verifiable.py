"""Micro-tasks whose answers can be checked automatically.

They let real language models compete without a human grader: arithmetic,
sorting, letter counting and e-mail extraction, each with a difficulty knob.
"""

from __future__ import annotations

import random
import re
from typing import Any, Callable

from .agent import normalize
from .hard_tasks import ANSWER_FORMAT, HARD_GENERATORS, check_hard
from .config import VerifiableCategory
from .market import Task

_INT = re.compile(r"-?\d[\d,]*")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_ANSWER = re.compile(r"answer\s*[:=]", re.IGNORECASE)

WORDS = (
    "river stone market garden letter paper orange silver basket rocket mirror tunnel "
    "pepper ladder carrot butter sister error banner cherry"
).split()
NAMES = "anna boris clara dmitri elena felix greta hugo irina jonas".split()
DOMAINS = "example.com mail.org startup.io shop.net data.dev".split()


def _arithmetic(rng: random.Random, d: float) -> tuple[str, Any, str]:
    digits = 2 + round(d * 2)
    a = rng.randint(10 ** (digits - 1), 10**digits - 1)
    b = rng.randint(3, 10 ** max(1, digits - 1) + 9)
    c = rng.randint(1, 999)
    op = rng.choice("+-")
    answer = a * b + c if op == "+" else a * b - c
    return f"Compute {a} * {b} {op} {c}.", answer, "int"


def _sorting(rng: random.Random, d: float) -> tuple[str, Any, str]:
    numbers = [rng.randint(-99, 999) for _ in range(5 + round(d * 15))]
    listed = ", ".join(map(str, numbers))
    return (
        f"Sort these numbers in ascending order and list them separated by commas: {listed}.",
        sorted(numbers),
        "list",
    )


def _counting(rng: random.Random, d: float) -> tuple[str, Any, str]:
    text = " ".join(rng.choice(WORDS) for _ in range(4 + round(d * 16)))
    letter = rng.choice("aerst")
    return (
        f"How many times does the letter '{letter}' appear in this text: \"{text}\"?",
        text.count(letter),
        "int",
    )


def _extraction(rng: random.Random, d: float) -> tuple[str, Any, str]:
    emails = {f"{rng.choice(NAMES)}.{rng.randint(1, 99)}@{rng.choice(DOMAINS)}" for _ in range(1 + round(d * 3))}
    noise = [
        f"visit {rng.choice(DOMAINS)}",
        f"ping @{rng.choice(NAMES)}",
        f"call +1-555-{rng.randint(1000, 9999)}",
        f"the {rng.choice(WORDS)} team",
    ]
    parts = list(emails) + rng.sample(noise, k=min(len(noise), 1 + round(d * 3)))
    rng.shuffle(parts)
    text = "; ".join(parts)
    return (
        f"Extract every e-mail address from this text and list them separated by commas: \"{text}\".",
        sorted(emails),
        "emails",
    )


GENERATORS: dict[str, Callable[[random.Random, float], tuple[str, Any, str]]] = {
    "arithmetic": _arithmetic,
    "sorting": _sorting,
    "counting": _counting,
    "extraction": _extraction,
    **HARD_GENERATORS,  # code, sql, invoice, business_days (see hard_tasks.py)
}


def extract_answer(response: str) -> str:
    """Text after the last ``ANSWER:`` marker, else the last non-empty line."""
    matches = list(_ANSWER.finditer(response))
    if matches:
        rest = response[matches[-1].end():].strip()
        return rest.splitlines()[0].strip() if rest else ""
    lines = [line.strip() for line in response.strip().splitlines() if line.strip()]
    return lines[-1] if lines else ""


def check_answer(kind: str, expected: Any, response: str) -> bool:
    if kind in ANSWER_FORMAT:
        return check_hard(kind, expected, response)
    answer = extract_answer(response)
    if kind == "int":
        found = _INT.findall(answer)
        return bool(found) and int(found[0].replace(",", "")) == expected
    if kind == "list":
        return [int(x) for x in re.findall(r"-?\d+", answer)] == expected
    if kind == "emails":
        return sorted({e.lower() for e in _EMAIL.findall(answer)}) == expected
    raise ValueError(f"unknown answer kind {kind!r}")


class VerifiableMarket:
    """A stream of auto-checkable tasks with prices growing with difficulty."""

    def __init__(
        self,
        categories: list[VerifiableCategory],
        tasks_per_generation: int,
        rng: random.Random,
        competitor_price_range: list[float] | None = None,
    ):
        unknown = [c.name for c in categories if c.name not in GENERATORS]
        if unknown:
            raise ValueError(f"no generator for categories {unknown}; available: {list(GENERATORS)}")
        self.specs = {c.name: c for c in categories}
        self.demand = normalize({c.name: c.demand for c in categories})
        self.tasks_per_generation = tasks_per_generation
        self.rng = rng
        self.competitor_price_range = competitor_price_range

    @property
    def categories(self) -> list[str]:
        return list(self.specs)

    def tasks_for(self, generation: int) -> list[Task]:
        names = list(self.demand)
        weights = [self.demand[c] for c in names]
        tasks = []
        for i in range(self.tasks_per_generation):
            category = self.rng.choices(names, weights)[0]
            difficulty = self.rng.random()
            prompt, answer, kind = GENERATORS[category](self.rng, difficulty)
            max_price = self.specs[category].base_price * (0.5 + difficulty)
            competitor = None
            if self.competitor_price_range is not None:
                competitor = max_price * self.rng.uniform(*self.competitor_price_range)
            tasks.append(
                Task(
                    id=f"g{generation}-t{i}",
                    generation=generation,
                    category=category,
                    difficulty=difficulty,
                    size=1.0,
                    max_price=max_price,
                    competitor_price=competitor,
                    payload={"prompt": prompt, "answer": answer, "kind": kind},
                )
            )
        return tasks
