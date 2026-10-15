"""2026-10-15: one answer to «is this about the board as it is» and «is this claim denied» (src/claim_scope.py)."""

import pytest

from src.claim_scope import about_now, conditional_before, denied_before, denied_in


@pytest.mark.parametrize("text,now", [
    ("Сейчас короткая рокировка невозможна.", True),
    ("Нет, рокироваться нельзя.", True),
    ("Если сыграть b3, рокировка станет возможна.", False),
    ("После Rg1 ладья нападает на ферзя.", False),
    ("По правилам рокировка запрещена через битое поле.", False),
    ("Если убрать слона, то здесь рокировка будет законна.", True),   # a now-word wins over the condition
])
def test_about_now_strict(text, now):
    assert about_now(text, strict=True) is now


def test_a_sentence_without_a_condition_is_about_now_unless_strict():
    assert about_now("Конь на f3 бьёт пешку e5.") is True
    assert about_now("Конь на f3 бьёт пешку e5.", strict=True) is False


def test_conditional_before_looks_only_before_the_claim():
    t = "Конь f3 бьёт e5, и после Nxe5 чёрные теряют пешку."
    assert conditional_before(t, t.index("бьёт")) is False
    assert conditional_before(t, t.index("теряют")) is True


@pytest.mark.parametrize("text,at,denied", [
    ("Ладья не бьёт h4.", "бьёт", True),
    ("Ладья не просто бьёт h4.", "бьёт", True),
    ("Слон нельзя взять.", "взять", True),
    ("The rook doesn't attack h4.", "attack", True),
    ("Ладья бьёт h4.", "бьёт", False),
])
def test_denied_before(text, at, denied):
    assert denied_before(text, text.index(at)) is denied


def test_denied_in_a_clause():
    assert denied_in("до h4 ей не достать") is True
    assert denied_in("бьёт по первой горизонтали") is False
