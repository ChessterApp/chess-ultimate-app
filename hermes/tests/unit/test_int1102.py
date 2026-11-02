"""Integration 02.11 (next-1031 + K1–K8): the patches the packages wrote for code they did not own, on new boards.

- K4 → K5's grammar: a piece «с X» is the mover of a told move only if it could reach the move's square
  (castle-rights #2, live 02.11: «чёрный конь с f6» was taken to have made 5.Nc3 → "the piece on c3 is White's").
- K6 → the answer check's issue texts: an undefended claim whose piece is not on the board now leaves no
  «defended (by )», and «no any queen» is not written. (K6's recapture hunk is covered by K5's own restatement rule.)
"""
from __future__ import annotations

import chess
import pytest

from src import answer_check as ac
from src.rewrite_proof import malformed


def _board(moves: str) -> chess.Board:
    b = chess.Board()
    for m in moves.split():
        b.push_san(m)
    return b


def _check(sentence, board, student=chess.WHITE):
    return ac.check_sentence(sentence, ac.CheckContext.from_fens([board.fen()], student_color=student))


# 1.e4 e5 2.d3 Nf6: Black's knight on f6 attacks e4, White's knight b1 can go to d2
OPEN_D3 = _board("e4 e5 d3 Nf6")
# 1.e4 e5 2.Nf3: White's knight on f3
KNIGHT_F3 = _board("e4 e5 Nf3")


@pytest.mark.unit
class TestPieceFromSquareIsTheMover:
    def test_another_piece_from_its_square_is_not_the_mover(self):
        s = "Подумай о Nd2 — заодно защитишь пешку e4, которую чёрный конь с f6 уже атакует."
        assert _check(s, OPEN_D3) == []

    def test_the_relation_of_that_piece_is_still_judged(self):
        s = "Подумай о Nd2 — заодно защитишь пешку e4, которую чёрный конь с f6 уже не атакует."
        assert any("f6" in i and "e4" in i for i in _check(s, OPEN_D3))

    def test_a_piece_that_can_reach_the_square_is_still_the_mover(self):
        # the knight from g1 did make Nf3; f3 does not attack d5
        s = "Сыграй Nf3: белый конь с g1 сразу нападает на пешку d5."
        assert _check(s, _board("e4 d5")) != []

    def test_could_go_geometry(self):
        from src.claim_grammar import _could_go
        sq = chess.parse_square
        assert not _could_go(chess.KNIGHT, sq("f6"), sq("c3"))
        assert _could_go(chess.KNIGHT, sq("b1"), sq("c3"))
        assert _could_go(chess.BISHOP, sq("f1"), sq("b5")) and not _could_go(chess.BISHOP, sq("f1"), sq("f5"))
        assert _could_go(chess.KING, sq("e1"), sq("g1")) and not _could_go(chess.KING, sq("e1"), sq("e3"))
        assert not _could_go(chess.ROOK, sq("a1"), sq("a1"))


@pytest.mark.unit
class TestIssueTexts:
    def test_a_pawn_capture_restated_after_words_is_not_a_recapture(self):
        # «cxd5, то есть ...: cxd5» names one move twice (1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.cxd5 is the exchange line)
        b = _board("d4 d5 c4 e6 Nc3 Nf6")
        issues = _check("Самое простое — cxd5, то есть сразу разменять центр: cxd5.", b)
        assert not any("after cxd5" in i for i in issues)
        assert all(not malformed(i) for i in issues)

    def test_a_real_pawn_recapture_pair_is_still_judged(self):
        # «Nxd5 exd5» with no e-pawn able to take back for Black (1.e4 d5 2.exd5 Nf6 3.Nc3): judged as before
        b = _board("e4 d5 exd5 Nf6 Nc3")
        assert any("exd5" in i for i in _check("После Nxd5 exd5 у чёрных всё в порядке.", b))

    def test_an_undefended_claim_about_another_piece_now_leaves_no_empty_defender_list(self):
        # 1.e4 e5 2.Nf3 d6 3.d4 Bg4 4.dxe5 Bxf3: «Конь f3 ничем не защищён» — the knight was defended; on f3 now
        # stands Black's bishop with no defender. Not «the bishop on f3 is defended (by )»; the wrong piece is told
        b = _board("e4 e5 Nf3 d6 d4 Bg4 dxe5")
        before = b.fen()
        b.push_san("Bxf3")
        ctx = ac.CheckContext.from_fens([b.fen(), before], student_color=chess.WHITE)
        issues = ac.check_sentence("Конь f3 ничем не защищён.", ctx)
        assert issues and all("(by )" not in i and not malformed(i) for i in issues)
        assert any("not a knight" in i for i in issues)

    def test_no_any_is_not_written(self):
        b = _board("e4 e5 Nf3 Nc6")
        for i in _check("Можно сразу Qxh7.", b) + _check("Хорош ход Qxf7#.", b):
            assert "no any" not in i
