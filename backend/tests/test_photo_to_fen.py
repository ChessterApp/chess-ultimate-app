"""Photo → FEN: reading the vision model's reply (2026-10-06).

Replies are the ones Gemini 3.8 Flash gave for the same board on
2026-10-06 — with the side to move, without it, and from Black's side.
"""

import chess
import pytest

from api.photo_to_fen import position_from_reply

PLACEMENT = "r2q1rk1/pp2bppp/4bn2/3P4/8/2N2N2/PP2BPPP/R2Q1RK1"


def test_placement_only_is_accepted_with_white_to_move():
    fen, known = position_from_reply(PLACEMENT)
    assert fen.split()[:2] == [PLACEMENT, "w"]
    assert known is False


def test_question_mark_means_unknown_side():
    fen, known = position_from_reply(f"{PLACEMENT} ?")
    assert fen.split()[1] == "w" and known is False


@pytest.mark.parametrize("side", ["w", "b"])
def test_visible_side_is_kept(side):
    fen, known = position_from_reply(f"{PLACEMENT} {side}")
    assert fen.split()[1] == side and known is True


def test_full_fen_from_an_older_prompt_is_read():
    fen, known = position_from_reply(f"{PLACEMENT} b - - 0 1")
    assert fen.split()[1] == "b" and known is True


def test_castling_only_where_king_and_rook_are_home():
    fen, _ = position_from_reply("r3k2r/8/8/8/8/8/8/R3K1R1 w")
    board = chess.Board(fen)
    assert board.has_queenside_castling_rights(chess.WHITE)
    assert not board.has_kingside_castling_rights(chess.WHITE)  # rook on g1
    assert board.has_kingside_castling_rights(chess.BLACK)
    assert board.ep_square is None


def test_side_in_check_decides_the_turn():
    # White's king is in check from the rook on e8: only White can be to move.
    fen, known = position_from_reply("4r1k1/8/8/8/8/8/8/4K3 b")
    assert fen.split()[1] == "w" and known is True


def test_prose_around_the_fen_is_ignored():
    fen, _ = position_from_reply(f"Here is the FEN:\n{PLACEMENT} w\n")
    assert fen.startswith(PLACEMENT + " w")


def test_garbage_is_none():
    assert position_from_reply("I cannot see a chessboard here.") is None
    assert position_from_reply("8/8/8/8/8/8/8/8 w") is None  # no kings
