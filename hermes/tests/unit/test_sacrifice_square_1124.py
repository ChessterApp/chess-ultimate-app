"""A sacrifice told with its square names a move of that piece to that square in the game on the board (tester 23.11:
«Решающая жертва ферзя на d8 отвлекла коня чёрных» about the Opera Game, where the queen was given up on b8 —
16.Qb8+ Nxb8 — and the rook mated on d8)."""

import chess
import chess.pgn
import io
import pytest

from src import answer_check_db as acd
from src.answer_check import CheckContext, check_sentence

OPERA = ('[White "Paul Morphy"]\n[Black "Duke Karl / Count Isouard"]\n[Event "Paris"]\n[Date "1858.??.??"]\n'
         '[Result "1-0"]\n\n1.e4 e5 2.Nf3 d6 3.d4 Bg4 4.dxe5 Bxf3 5.Qxf3 dxe5 6.Bc4 Nf6 7.Qb3 Qe7 8.Nc3 c6 9.Bg5 b5 '
         '10.Nxb5 cxb5 11.Bxb5+ Nbd7 12.O-O-O Rd8 13.Rxd7 Rxd7 14.Rd1 Qe6 15.Bxd7+ Nxd7 16.Qb8+ Nxb8 17.Rd8# 1-0')


def _final(pgn):
    game = chess.pgn.read_game(io.StringIO(pgn))
    board = game.board()
    for mv in game.mainline_moves():
        board.push(mv)
    return board.fen()


def _ctx():
    ctx = CheckContext.from_fens([_final(OPERA)], [OPERA], question="Разбери эту партию")
    acd.note_board_game(ctx, OPERA)
    return ctx


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Финальный удар. Решающая жертва ферзя на d8 отвлекла коня чёрных, позволив ладье поставить мат.",
    "Белые пожертвовали ферзя на d8 и поставили мат.",
    "The queen sacrifice on d8 deflected the knight.",
])
def test_a_sacrifice_on_a_square_its_piece_never_went_to_is_cut_with_the_real_one(sentence):
    issues = acd.sacrifice_issues(sentence, _ctx())
    assert issues and "no queen went to d8" in issues[0] and "16.Qb8+ 16...Nxb8" in issues[0]
    assert any("16.Qb8+" in i for i in check_sentence(sentence, _ctx()))


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Решающая жертва ферзя на b8 отвлекла коня чёрных.",
    "Белые пожертвовали коня на b5, чтобы вскрыть линии.",
    "Жертва ладьи на d7 вскрыла линию.",
    "Morphy sacrificed his queen on b8.",
    "Можно было пожертвовать ферзя на d8, но это хуже.",
    "Ладья поставила мат на d8 при поддержке слона g5.",
])
def test_a_true_sacrifice_or_a_what_if_is_left_alone(sentence):
    assert acd.sacrifice_issues(sentence, _ctx()) == []


@pytest.mark.unit
def test_no_game_on_the_board_nothing_is_judged():
    assert acd.sacrifice_issues("Жертва ферзя на d8.", CheckContext()) == []


@pytest.mark.unit
def test_it_ships_on_and_can_be_switched(monkeypatch):
    from src import config

    assert acd.mode("sacrifice") == "on"
    monkeypatch.setattr(config, "COACH_SACRIFICE_CHECK", "off")
    assert acd.game_db_issues("жертва ферзя на d8.", "Жертва ферзя на d8.", _ctx()) == []
