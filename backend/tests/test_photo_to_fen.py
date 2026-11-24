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


def test_a_misread_reply_is_asked_again(monkeypatch):
    """Two black kings (a white back rank read as black) is not a position: one more try."""
    import api.photo_to_fen as pf
    from flask import Flask

    replies = iter([f"{PLACEMENT[:-8]}r2Q1rk1 ?", f"{PLACEMENT} ?"])

    class Resp:
        ok = True
        status_code = 200

        def __init__(self, text):
            self._text = text

        def json(self):
            return {"choices": [{"message": {"content": self._text}}]}

    calls = []
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setattr(pf.requests, "post", lambda *a, **k: calls.append(1) or Resp(next(replies)))
    app = Flask(__name__)
    app.register_blueprint(pf.photo_fen_bp)
    res = app.test_client().post("/api/convert-image", json={"image": "aGVsbG8="})
    assert res.status_code == 200 and len(calls) == 2
    assert res.get_json()["fen"].startswith(PLACEMENT + " w")


def test_a_side_shown_that_cannot_move_is_doubted():
    # Tester 20.11: the black king read on g8 (it stood on f8), in check from the queen with White to move.
    from api.photo_to_fen import shown_side_impossible

    assert shown_side_impossible("6k1/8/8/8/8/8/8/6QK w")
    assert not shown_side_impossible("6k1/8/8/8/8/8/8/6QK ?")
    assert not shown_side_impossible("6k1/8/8/8/8/8/8/6QK b")


def _route(monkeypatch, texts):
    import api.photo_to_fen as pf
    from flask import Flask

    replies = iter(texts)

    class Resp:
        ok = True
        status_code = 200

        def __init__(self, text):
            self._text = text

        def json(self):
            return {"choices": [{"message": {"content": self._text}}]}

    calls = []
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setattr(pf.requests, "post", lambda *a, **k: calls.append(1) or Resp(next(replies)))
    app = Flask(__name__)
    app.register_blueprint(pf.photo_fen_bp)
    return app.test_client().post("/api/convert-image", json={"image": "aGVsbG8="}), calls


def test_a_side_that_cannot_move_is_read_again_then_doubted(monkeypatch):
    import api.photo_to_fen as pf

    misread = "6k1/8/8/8/8/8/8/6QK w"
    res, calls = _route(monkeypatch, [misread] * pf.PHOTO_FEN_ATTEMPTS)
    data = res.get_json()
    assert res.status_code == 200 and len(calls) == pf.PHOTO_FEN_ATTEMPTS
    assert data["doubt"] is True and data["turn_known"] is False and data["fen"].split()[1] == "b"


def test_read_again_right_is_no_doubt(monkeypatch):
    res, calls = _route(monkeypatch, ["6k1/8/8/8/8/8/8/6QK w", "5k2/8/8/8/8/8/8/6QK w"])
    data = res.get_json()
    assert len(calls) == 2 and "doubt" not in data and data["turn_known"] is True and data["fen"].startswith("5k2/")


# Tester 23.11: the same photo — the black king read on g8 (it stood on f8), no side named; only Black can be to move
# (White's turn would leave Black in check), and Black is in check from the queen g3 and the bishop h7 at once.
GERMAN_1123 = "4r1k1/1b3p1B/pp3q2/8/P1pP4/2P2pQ1/1P5P/4rRK1"


def test_a_double_check_is_read_again_then_doubted(monkeypatch):
    import api.photo_to_fen as pf

    res, calls = _route(monkeypatch, [f"{GERMAN_1123} ?"] * pf.PHOTO_FEN_ATTEMPTS)
    data = res.get_json()
    assert res.status_code == 200 and len(calls) == pf.PHOTO_FEN_ATTEMPTS
    assert data["doubt"] is True and data["doubt_reason"] == "double_check" and data["turn_known"] is False


def test_a_double_check_read_again_right_is_no_doubt(monkeypatch):
    res, calls = _route(monkeypatch, [f"{GERMAN_1123} ?", "4rk2/1b3p1B/pp3q2/8/P1pP4/2P2pQ1/1P5P/4rRK1 ?"])
    data = res.get_json()
    assert len(calls) == 2 and "doubt" not in data and data["fen"].startswith("4rk2/")


def test_a_side_doubt_says_its_reason(monkeypatch):
    import api.photo_to_fen as pf

    res, _ = _route(monkeypatch, ["6k1/8/8/8/8/8/8/6QK w"] * pf.PHOTO_FEN_ATTEMPTS)
    assert res.get_json()["doubt_reason"] == "side"


def test_one_check_is_no_doubt():
    from api.photo_to_fen import double_check

    assert double_check(f"{GERMAN_1123} b - - 0 1")
    assert not double_check("6k1/8/8/8/8/8/8/6QK b - - 0 1")
