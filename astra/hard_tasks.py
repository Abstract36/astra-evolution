"""Harder auto-checked tasks: writing code against hidden tests, SQL, messy extraction, date arithmetic.

These are closer to paid work than the micro-tasks in ``verifiable.py``, and
no single model is expected to win all of them.

Model-written code is executed, so it runs in a separate Python process with
a time limit, memory and file-size limits, an empty environment and only a
small allow-list of modules, after a static check of the source. This is a
light sandbox for research on cooperative models, not a security boundary
against code written to attack it.
"""

from __future__ import annotations

import ast
import calendar
import json
import random
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Code: implement a function, checked by hidden tests


def _rle(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        out.append(f"{s[i]}{j - i}")
        i = j
    return "".join(out)


def _ipv4(s: str) -> bool:
    parts = s.split(".")
    return len(parts) == 4 and all(p.isdigit() and str(int(p)) == p and 0 <= int(p) <= 255 for p in parts)


def _merge(intervals: list[list[int]]) -> list[list[int]]:
    merged: list[list[int]] = []
    for a, b in sorted(intervals):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


def _roman(n: int) -> str:
    table = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
             (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for value, symbol in table:
        while n >= value:
            out, n = out + symbol, n - value
    return out


def _brackets(s: str) -> bool:
    pairs, stack = {")": "(", "]": "[", "}": "{"}, []
    for ch in s:
        if ch in "([{":
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack.pop() != pairs[ch]:
                return False
    return not stack


def _snake(s: str) -> str:
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


def _second_largest(nums: list[int]) -> int | None:
    distinct = sorted(set(nums), reverse=True)
    return distinct[1] if len(distinct) > 1 else None


def _rng_word(rng: random.Random, letters: str = "aabbbcd", n: int = 8) -> str:
    return "".join(rng.choice(letters) for _ in range(rng.randint(0, n)))


# name, signature, specification, reference, random-input generator, difficulty
CODE_SPECS: list[tuple[str, str, str, Callable, Callable[[random.Random], tuple], float]] = [
    ("run_length_encode", "run_length_encode(s: str) -> str",
     "Encode runs of repeated characters as the character followed by the run length, "
     "e.g. 'aaabcc' -> 'a3b1c2'. The empty string encodes to ''.",
     _rle, lambda r: (_rng_word(r),), 0.2),
    ("second_largest", "second_largest(nums: list[int]) -> int | None",
     "Return the second largest DISTINCT value, or None if there is none.",
     _second_largest, lambda r: ([r.randint(-5, 5) for _ in range(r.randint(0, 6))],), 0.3),
    ("balanced_brackets", "balanced_brackets(s: str) -> bool",
     "Return True if every (, [ and { is closed by the matching bracket in the right order. "
     "Other characters are ignored.",
     _brackets, lambda r: ("".join(r.choice("()[]{}a") for _ in range(r.randint(0, 10))),), 0.4),
    ("to_roman", "to_roman(n: int) -> str",
     "Convert an integer from 1 to 3999 to a Roman numeral using subtractive notation (4 -> 'IV').",
     _roman, lambda r: (r.randint(1, 3999),), 0.5),
    ("is_valid_ipv4", "is_valid_ipv4(s: str) -> bool",
     "Return True if s is a dotted IPv4 address: four decimal numbers 0-255 without leading zeros "
     "(so '01.2.3.4' is invalid) and nothing else.",
     _ipv4, lambda r: (r.choice([
         f"{r.randint(0, 300)}.{r.randint(0, 255)}.{r.randint(0, 255)}.{r.randint(0, 255)}",
         f"0{r.randint(1, 9)}.1.1.1", f"{r.randint(0, 255)}.{r.randint(0, 255)}.{r.randint(0, 255)}",
         f"1.2.3.4.{r.randint(0, 9)}", f"1.2.3.{r.choice(['a', '', ' 4', '-1'])}",
     ]),), 0.6),
    ("merge_intervals", "merge_intervals(intervals: list[list[int]]) -> list[list[int]]",
     "Merge overlapping or touching closed intervals [a, b] and return them sorted by start, "
     "e.g. [[5, 6], [1, 3], [2, 4]] -> [[1, 4], [5, 6]]; [[1, 2], [2, 3]] -> [[1, 3]].",
     _merge, lambda r: ([sorted([r.randint(0, 20), r.randint(0, 20)]) for _ in range(r.randint(0, 6))],), 0.7),
    ("camel_to_snake", "camel_to_snake(name: str) -> str",
     "Convert CamelCase or camelCase to snake_case, keeping acronyms together: "
     "'parseHTTPResponse' -> 'parse_http_response', 'UserID' -> 'user_id', 'already_snake' unchanged.",
     _snake, lambda r: (r.choice(["parseHTTPResponse", "UserID", "already_snake", "getX", "simple",
                                  "HTMLParser", "loadJSONData", "ab2Cd", "XMLHttpRequest"]),), 0.8),
]

ALLOWED_MODULES = {"math", "re", "itertools", "collections", "functools", "string", "heapq", "bisect", "typing"}
FORBIDDEN_NAMES = {
    "open", "exec", "eval", "compile", "__import__", "input", "globals", "locals", "vars",
    "getattr", "setattr", "delattr", "breakpoint", "exit", "quit", "help", "memoryview",
}

_HARNESS = """
import json, sys
_tests = json.loads(sys.stdin.read())
_ok = 0
for _args, _want in _tests:
    try:
        _got = {name}(*_args)
        if isinstance(_got, tuple):
            _got = list(_got)
        _ok += _got == _want
    except Exception:
        pass
print(json.dumps({{"passed": _ok, "total": len(_tests)}}))
"""


def extract_code(response: str, language: str = "python") -> str:
    """The last fenced code block (```python ... ```), else the whole response."""
    blocks = re.findall(r"```(?:" + language + r")?[ \t]*\n(.*?)```", response, re.S | re.I)
    return blocks[-1].strip() if blocks else response.strip()


def static_check(code: str) -> str | None:
    """Return a reason to refuse the code, or None if it may run."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"syntax error: {exc.msg}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]]
        else:
            names = []
        if any(n not in ALLOWED_MODULES for n in names):
            return f"import not allowed: {names}"
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            return f"name not allowed: {node.id}"
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return f"attribute not allowed: {node.attr}"
    return None


def _limits() -> None:  # runs in the child process before the code
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))


def run_code_tests(code: str, name: str, tests: list[list[Any]], timeout: float = 10.0) -> bool:
    if static_check(code) is not None:
        return False
    script = code + "\n" + _HARNESS.format(name=name)
    with tempfile.TemporaryDirectory() as tmp:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-S", "-c", script],
                input=json.dumps(tests),
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmp,
                env={},
                preexec_fn=_limits if sys.platform != "win32" else None,
            )
        except subprocess.TimeoutExpired:
            return False
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return False
    return result["total"] > 0 and result["passed"] == result["total"]


def _code_task(rng: random.Random, d: float) -> tuple[str, Any, str]:
    candidates = [s for s in CODE_SPECS if abs(s[5] - d) <= 0.35] or CODE_SPECS
    name, signature, spec, reference, make, _ = rng.choice(candidates)
    tests = []
    for _ in range(12):
        args = make(rng)
        tests.append([list(args), reference(*args)])
    prompt = (
        f"Write a Python function `{signature}`.\n{spec}\n"
        "Use only the standard library modules math, re, itertools, collections, functools, string, heapq, bisect. "
        "It will be checked by hidden unit tests."
    )
    return prompt, {"name": name, "tests": tests}, "code"


# ---------------------------------------------------------------------------
# SQL: a query over a small SQLite table


CUSTOMERS = ["acme", "globex", "initech", "umbrella", "stark", "wayne"]
STATUSES = ["paid", "pending", "refunded"]


def _sql_task(rng: random.Random, d: float) -> tuple[str, Any, str]:
    rows = []
    for i in range(1, 6 + round(d * 14)):
        rows.append(
            (i, rng.choice(CUSTOMERS[: 3 + round(d * 3)]), round(rng.uniform(10, 500), 2),
             rng.choice(STATUSES), f"2026-0{rng.randint(1, 4)}-{rng.randint(1, 28):02d}")
        )
    customer = rng.choice([r[1] for r in rows])
    questions = [
        (f"What is the total amount of paid orders of customer '{customer}'? Return one number rounded to 2 decimals "
         "(0 if there are none).",
         f"SELECT ROUND(COALESCE(SUM(amount), 0), 2) FROM orders WHERE status = 'paid' AND customer = '{customer}'"),
        ("How many orders are there per status? Return status and count, ordered by status.",
         "SELECT status, COUNT(*) FROM orders GROUP BY status ORDER BY status"),
        ("Which customer has the highest total amount of paid orders? Return only the customer name.",
         "SELECT customer FROM orders WHERE status = 'paid' GROUP BY customer ORDER BY SUM(amount) DESC LIMIT 1"),
        ("What is the average amount of orders created in March 2026, rounded to 2 decimals?",
         "SELECT ROUND(AVG(amount), 2) FROM orders WHERE created BETWEEN '2026-03-01' AND '2026-03-31'"),
        ("For each customer with at least two paid orders, return the customer and the number of paid orders, "
         "ordered by that number descending, then by customer.",
         "SELECT customer, COUNT(*) AS n FROM orders WHERE status = 'paid' GROUP BY customer "
         "HAVING COUNT(*) >= 2 ORDER BY n DESC, customer"),
    ]
    question, reference = questions[min(len(questions) - 1, int(d * len(questions)))]
    schema = "CREATE TABLE orders (id INTEGER, customer TEXT, amount REAL, status TEXT, created TEXT);"
    inserts = "\n".join(f"INSERT INTO orders VALUES ({r[0]}, '{r[1]}', {r[2]}, '{r[3]}', '{r[4]}');" for r in rows)
    expected = _run_sql(schema, inserts, reference)
    prompt = f"SQLite table and data:\n{schema}\n{inserts}\n\nQuestion: {question}\nWrite one SQLite SELECT query that answers it."
    return prompt, {"schema": schema, "data": inserts, "rows": expected}, "sql"


def _deny_writes(action: int, *args: Any) -> int:
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def _run_sql(schema: str, inserts: str, query: str) -> list[list[Any]] | None:
    db = sqlite3.connect(":memory:")
    try:
        db.executescript(schema + "\n" + inserts)
        db.set_authorizer(_deny_writes)
        db.set_progress_handler(lambda: 1, 200_000)  # abort runaway queries
        rows = db.execute(query).fetchall()
        return [[round(v, 2) if isinstance(v, float) else v for v in row] for row in rows]
    except sqlite3.Error:
        return None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Messy extraction: invoice fields to JSON


VENDORS = ["Nordic Timber OU", "Baltic Supply AB", "Alpine Tools GmbH", "Atlantic Freight Ltd"]


def _money(rng: random.Random, value: float, currency: str, d: float) -> str:
    whole, cents = f"{value:,.2f}".split(".")
    styles = [
        f"{currency} {whole}.{cents}",
        f"{whole.replace(',', '.')},{cents} {currency}",
        f"{whole.replace(',', ' ')},{cents} {'EUR' if currency == 'EUR' else currency}",
        f"{'€' if currency == 'EUR' else '$' if currency == 'USD' else currency + ' '}{whole}.{cents}",
    ]
    return styles[min(len(styles) - 1, int(rng.random() * (1 + d * 3)))]


def _date_text(rng: random.Random, day: date, d: float) -> str:
    styles = [
        day.isoformat(),
        f"{calendar.month_name[day.month]} {day.day}, {day.year}",
        f"{day.day} {calendar.month_abbr[day.month]} {day.year}",
        f"{day.day}.{day.month:02d}.{day.year}",
    ]
    return styles[min(len(styles) - 1, int(rng.random() * (1 + d * 3)))]


def _invoice_task(rng: random.Random, d: float) -> tuple[str, Any, str]:
    currency = rng.choice(["EUR", "USD", "GBP"])
    total = round(rng.uniform(50, 25000), 2)
    due = date(2026, 1, 1) + timedelta(days=rng.randint(0, 300))
    number = f"INV-{rng.randint(1000, 9999)}-{rng.choice('ABCDE')}"
    lines = [
        f"From: {rng.choice(VENDORS)}",
        f"Our ref {number}" if d > 0.5 else f"Invoice number: {number}",
        f"Subtotal {_money(rng, round(total / 1.22, 2), currency, d)}" if d > 0.3 else "",
        f"Amount due: {_money(rng, total, currency, d)}",
        f"Please pay by {_date_text(rng, due, d)}.",
        f"Previous balance settled on {_date_text(rng, due - timedelta(days=40), d)}." if d > 0.6 else "",
    ]
    lines = [line for line in lines if line]
    rng.shuffle(lines)
    expected = {"invoice_number": number, "total": total, "currency": currency, "due_date": due.isoformat()}
    prompt = (
        "Extract from this invoice text the invoice number, the total amount due, its currency (ISO code) "
        "and the payment due date (YYYY-MM-DD). Reply on the last line as "
        'ANSWER: {"invoice_number": ..., "total": ..., "currency": ..., "due_date": ...}\n\n' + "\n".join(lines)
    )
    return prompt, expected, "invoice"


# ---------------------------------------------------------------------------
# Business days


def _business_days_task(rng: random.Random, d: float) -> tuple[str, Any, str]:
    start = date(2026, 1, 1) + timedelta(days=rng.randint(0, 330))
    n = rng.randint(3, 10 + round(d * 80))
    day, left = start, n
    while left:
        day += timedelta(days=1)
        if day.weekday() < 5:
            left -= 1
    weekday = calendar.day_name[start.weekday()]
    prompt = (
        f"What date is {n} business days (Monday to Friday, no holidays) after {weekday} {start.isoformat()}? "
        "Do not count the start date. Answer as YYYY-MM-DD."
    )
    return prompt, day.isoformat(), "date"


HARD_GENERATORS: dict[str, Callable[[random.Random, float], tuple[str, Any, str]]] = {
    "code": _code_task,
    "sql": _sql_task,
    "invoice": _invoice_task,
    "business_days": _business_days_task,
}

# How the answer must be formatted, per kind (used by the solver's instructions).
ANSWER_FORMAT = {"code": "code", "sql": "sql", "invoice": "marker", "date": "marker"}


def check_hard(kind: str, expected: Any, response: str) -> bool:
    from .verifiable import extract_answer

    if kind == "code":
        return run_code_tests(extract_code(response, "python"), expected["name"], expected["tests"])
    if kind == "sql":
        query = extract_code(response, "sql")
        if "ANSWER:" in query.upper() and "```" not in response:
            query = extract_answer(response)
        rows = _run_sql(expected["schema"], expected["data"], query.rstrip(";"))
        return rows is not None and rows == expected["rows"]
    if kind == "invoice":
        match = re.search(r"\{.*\}", extract_answer(response) or response, re.S)
        if not match:
            return False
        try:
            got = json.loads(match.group(0))
            return (
                str(got.get("invoice_number", "")).strip() == expected["invoice_number"]
                and abs(float(str(got.get("total", "nan")).replace(",", "")) - expected["total"]) < 0.01
                and str(got.get("currency", "")).strip().upper() == expected["currency"]
                and str(got.get("due_date", "")).strip() == expected["due_date"]
            )
        except (ValueError, TypeError):
            return False
    if kind == "date":
        found = re.search(r"\d{4}-\d{2}-\d{2}", extract_answer(response))
        return bool(found) and found.group(0) == expected
    raise ValueError(f"unknown kind {kind!r}")
