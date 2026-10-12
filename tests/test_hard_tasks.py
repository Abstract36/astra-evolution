import json
import random

import pytest

from astra.hard_tasks import (
    CODE_SPECS,
    HARD_GENERATORS,
    _run_sql,
    check_hard,
    extract_code,
    run_code_tests,
    static_check,
)
from astra.verifiable import check_answer

GOOD_RLE = '''
def run_length_encode(s):
    out, i = [], 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        out.append(s[i] + str(j - i))
        i = j
    return "".join(out)
'''


def rle_tests():
    reference = next(spec for spec in CODE_SPECS if spec[0] == "run_length_encode")[3]
    return [[[s], reference(s)] for s in ["", "a", "aaabcc", "abc", "zzzzzz"]]


def test_correct_code_passes_and_wrong_code_fails():
    assert run_code_tests(GOOD_RLE, "run_length_encode", rle_tests())
    wrong = "def run_length_encode(s):\n    return s\n"
    assert not run_code_tests(wrong, "run_length_encode", rle_tests())
    assert not run_code_tests("def run_length_encode(s) return s", "run_length_encode", rle_tests())


@pytest.mark.parametrize(
    "code",
    [
        "import os\ndef f(s):\n    return os.listdir('.')",
        "def f(s):\n    return open('/etc/passwd').read()",
        "def f(s):\n    return __import__('os')",
        "def f(s):\n    return ().__class__.__bases__",
        "from subprocess import run\ndef f(s):\n    return 1",
    ],
)
def test_dangerous_code_is_refused_before_running(code):
    assert static_check(code) is not None
    assert not run_code_tests(code, "f", [[["x"], 1]])


def test_runaway_code_is_stopped():
    loop = "def f(s):\n    while True:\n        pass\n"
    assert not run_code_tests(loop, "f", [[["x"], 1]], timeout=3)


def test_extract_code_takes_the_last_block():
    text = "Idea:\n```python\nx = 1\n```\nFinal:\n```python\ndef f():\n    return 2\n```"
    assert extract_code(text) == "def f():\n    return 2"
    assert extract_code("SELECT 1;", "sql") == "SELECT 1;"


@pytest.mark.parametrize("category", sorted(HARD_GENERATORS))
def test_generated_tasks_have_valid_expected_answers(category):
    rng = random.Random(4)
    for difficulty in (0.0, 0.5, 1.0):
        prompt, expected, kind = HARD_GENERATORS[category](rng, difficulty)
        assert prompt
        if kind == "code":
            assert expected["tests"] and all(len(t) == 2 for t in expected["tests"])
        elif kind == "sql":
            assert expected["rows"] is not None
        elif kind == "invoice":
            answer = "ANSWER: " + json.dumps(expected)
            assert check_answer(kind, expected, answer)
            assert not check_answer(kind, expected, "ANSWER: " + json.dumps({**expected, "total": 1}))
        elif kind == "date":
            assert check_answer(kind, expected, f"ANSWER: {expected}")
            assert not check_answer(kind, expected, "ANSWER: 1999-01-01")


def test_sql_answers_are_checked_by_running_them():
    rng = random.Random(1)
    _, expected, _ = HARD_GENERATORS["sql"](rng, 0.2)
    count = _run_sql(expected["schema"], expected["data"], "SELECT COUNT(*) FROM orders")
    assert count and count[0][0] > 0
    assert not check_hard("sql", expected, "```sql\nSELECT 'nonsense'\n```")


def test_sql_cannot_modify_anything():
    schema = "CREATE TABLE t (x INTEGER);"
    assert _run_sql(schema, "INSERT INTO t VALUES (1);", "DELETE FROM t") is None
    assert _run_sql(schema, "", "ATTACH DATABASE '/tmp/x.db' AS other") is None
    assert _run_sql(schema, "INSERT INTO t VALUES (1);", "SELECT x FROM t") == [[1]]
