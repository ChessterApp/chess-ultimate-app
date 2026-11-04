"""K2 (fix1102, verify1102 B2): a block claim is judged on the board it refers to.

block_kind judged «Закройся конём на c6, хотя после Qxc6+ конь теряется» on the scene of the LATER line (Qxc6+ walked on
a board without the proposed knight, the turn changed to make it legal) and «Qf3+ … перекрывает королю выход» as a block
of the check (it is the checker taking the king's way out). Two mechanisms:

* a scene set by a line written after the block word may clear a claim but never condemns it when that line does not
  follow on from the board before the sentence move by move (turn changed, boards jumped) or lands on the very square
  the sentence blocks on;
* a block verb whose object is the king's way out («королю выход», «поля отхода», "the king's escape") is not a block
  of the check.

All boards here are new (not the reported ones). Positive cases are false claims that must still be cut, negative ones
true sentences that must pass.
"""
from __future__ import annotations

import chess
import pytest

from src.answer_check import CheckContext, _BLOCK_ESCAPE, check_sentence

# Black to move, not in check: the bishop on g2 hits the rook a8 down the long diagonal (d5, c6, b7 empty), and Qa4+ or
# Bxc6+ would check along a4-e8 / c6-e8.
LONG_DIAG_B = "rnbqkbnr/p3pppp/8/8/8/6P1/PP2PPBP/RNBQK1NR b KQkq - 0 6"
LONG_DIAG_W = "rnbqkbnr/p3pppp/8/8/8/6P1/PP2PPBP/RNBQK1NR w KQkq - 0 6"
# The same with the queen already on a4: Black is in check now; blocks Nc6, Nd7, Bd7, Qd7.
IN_CHECK = "rnbqkbnr/p3pppp/8/8/Q7/6P1/PP2PPBP/RNB1K1NR b KQkq - 1 6"
# Black to move; Qf1+ checks the king on g1 from the next square: no block, only Kxf1.
ADJ_CHECK = "6k1/8/8/8/2q5/8/6PP/6K1 b - - 0 1"
# Black to move; Nd3+ would fork the king e1 and the rook b2 — a knight's check, nothing blocks it.
KNIGHT_FORK = "4k3/8/8/4n3/8/8/1R3PPP/4K3 b - - 0 1"


def _check(fen: str, sentence: str, language=None) -> list[str]:
    ctx = CheckContext.from_fens([fen])
    if language:
        ctx.language = language
    return check_sentence(sentence, ctx)


# ── a later line read without the block the sentence proposed first ─────────────────────────────────────────────────
@pytest.mark.parametrize("fen, sentence", [
    # the later capture lands on the block's own square (and was walked with the turn changed)
    (LONG_DIAG_B, "Закройся конём на c6, хотя после Bxc6+ конь всё равно теряется."),
    (LONG_DIAG_B, "Самое упорное — перекрыть диагональ конём на c6, хотя после Bxc6+ конь пропадает."),
    # the turn is not changed (White to move), but Bxc6+ takes on the very square the sentence blocks on
    (LONG_DIAG_W, "Закройся конём на c6, хотя после Bxc6+ конь теряется."),
    # the later check does not touch the block square, but it was walked with Black's move skipped
    (LONG_DIAG_B, "Закройся ферзём на d5, хотя после Qa4+ всё равно плохо."),
    # the block named as a move
    (LONG_DIAG_B, "Закройся ходом Nc6, хотя после Bxc6+ конь всё равно теряется."),
])
def test_a_later_line_without_the_block_does_not_condemn_it(fen, sentence):
    assert _check(fen, sentence) == []


@pytest.mark.parametrize("fen, sentence", [
    # the later line follows on from the board (White to move) and leaves the block square alone: its scene is the
    # board the block answers
    (LONG_DIAG_W, "Закройся ладьёй на d7 в ответ на Qa4+."),
    # a line written before the block word: the board right after it (a later move the walk could not follow does
    # not take that board away, even when it names the block's square)
    (LONG_DIAG_W, "На Qa4+ закройся ладьёй на d7."),
    (LONG_DIAG_W, "На Qa4+ закройся ладьёй на d7, хотя после Rxd7 всё равно плохо."),
    # the board on the screen is in check: a later line does not take it away
    (IN_CHECK, "Закройся ладьёй на d7."),
    (IN_CHECK, "Закройся ладьёй на d7, а после Qxd7+ король уходит."),
    (IN_CHECK, "Закройся ферзём на c6, хотя после Bxc6+ всё равно плохо."),
    (IN_CHECK, "Закрой короля ладьёй на d7."),
])
def test_a_false_block_on_the_right_board_is_still_cut(fen, sentence):
    assert any("cannot block this check" in x for x in _check(fen, sentence))


@pytest.mark.parametrize("sentence", [
    "Закройся слоном на d7.",
    "Закройся конём на c6, хотя после Bxc6+ конь всё равно теряется.",
    "Закройся слоном на поле d7.",
])
def test_true_blocks_on_the_board_in_check_pass(sentence):
    assert _check(IN_CHECK, sentence) == []


def test_a_false_block_on_a_named_square_is_still_cut():
    # «на поле d7»: the noun of the square is not the king's way out
    issues = _check(IN_CHECK, "Закройся ладьёй на поле d7.")
    assert issues and "cannot block this check" in issues[0]


# ── the checker taking the king's way out is not a block of the check ───────────────────────────────────────────────
@pytest.mark.parametrize("fen, sentence", [
    (ADJ_CHECK, "Qf1+ даёт шах и перекрывает королю выход на f2."),
    (ADJ_CHECK, "Qf1+ отнимает поле f2, и заодно закрывает королю все поля."),
    (ADJ_CHECK, "Смотри: Qf1+ бьёт по королю и перекрывает белому королю пути отхода."),
    (KNIGHT_FORK, "Nd3+ бьёт и короля, и ладью b2, а заодно закрывает королю поле d2."),
])
def test_the_king_cut_off_is_not_a_block_claim(fen, sentence):
    assert _check(fen, sentence) == []


@pytest.mark.parametrize("sentence", [
    "Qf1+ gives check, and the queen is there to block the king's escape.",
    "Qf1+ gives check and is a block of the king's escape.",
])
def test_the_king_cut_off_in_english_is_not_a_block_claim(sentence):
    assert _check(ADJ_CHECK, sentence, language="en") == []


def test_a_block_claim_in_english_is_still_cut():
    issues = _check(ADJ_CHECK, "Qf1+ gives check, and White can block it with the rook.", language="en")
    assert issues and "cannot be blocked" in issues[0]


@pytest.mark.parametrize("fen, sentence", [
    # a real block claim after the same checks is still judged
    (ADJ_CHECK, "Qf1+ — и белым придётся закрыться ладьёй."),
    (ADJ_CHECK, "Qf1+, и шах можно перекрыть."),
    (KNIGHT_FORK, "Nd3+, и белые закроются ладьёй на d2."),
])
def test_a_block_claim_after_an_unblockable_check_is_still_cut(fen, sentence):
    issues = _check(fen, sentence)
    assert issues and "cannot be blocked" in issues[0]


@pytest.mark.parametrize("after, escape", [
    (" королю выход.", True),
    (" чёрному королю последнее поле.", True),
    (" путь отступления", True),
    (" the king's escape", True),
    (" шах конём", False),
    (" слоном на поле d7", False),
    (" путём Bd7", False),
    (" короля конём", False),
    (" полезно", False),
])
def test_the_escape_object(after, escape):
    assert bool(_BLOCK_ESCAPE.match(after.replace("ё", "е"))) is escape
