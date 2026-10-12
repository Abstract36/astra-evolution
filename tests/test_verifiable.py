import random

import pytest

from astra.config import VerifiableCategory
from astra.verifiable import GENERATORS, VerifiableMarket, check_answer, extract_answer


def format_answer(kind, answer):
    if kind == "int":
        return str(answer)
    return ", ".join(map(str, answer))


@pytest.mark.parametrize("category", sorted(GENERATORS))
def test_expected_answers_pass_and_wrong_answers_fail(category):
    rng = random.Random(1)
    for difficulty in (0.0, 0.5, 1.0):
        prompt, answer, kind = GENERATORS[category](rng, difficulty)
        assert prompt
        assert check_answer(kind, answer, f"Let me think.\nANSWER: {format_answer(kind, answer)}")
        assert not check_answer(kind, answer, "ANSWER: 99999, wrong@nowhere.xx")


def test_answer_extraction():
    assert extract_answer("steps...\nAnswer: 12\nthanks") == "12"
    assert extract_answer("ANSWER: 1\nfinal ANSWER: 2") == "2"
    assert extract_answer("no marker\n\n  7  \n") == "7"
    assert extract_answer("") == ""


def test_numbers_with_thousands_separators():
    assert check_answer("int", 12345, "ANSWER: 12,345")


def test_market_tasks_are_reproducible_and_priced_by_difficulty():
    cats = [VerifiableCategory(c) for c in GENERATORS]
    a = VerifiableMarket(cats, 20, random.Random(3)).tasks_for(0)
    b = VerifiableMarket(cats, 20, random.Random(3)).tasks_for(0)
    assert [t.payload for t in a] == [t.payload for t in b]
    for t in a:
        assert t.max_price == pytest.approx(4.0 * (0.5 + t.difficulty))


def test_unknown_category_is_rejected():
    with pytest.raises(ValueError):
        VerifiableMarket([VerifiableCategory("poetry")], 5, random.Random(0))
