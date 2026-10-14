"""«Моменты»: a game review as typed, board-checked steps (src/review_moments.py, P3b)."""

import json

import chess
import pytest

from src.review_moments import MAX_MOMENTS, build_review_moments
from src.tool_summaries import build_summary

pytestmark = pytest.mark.unit

# 13.Nc7+ forks the king on e8 and the rook on a8; White played 13.Ke2.
FORK_FEN = "r3k3/8/8/1N6/8/8/8/4K3 w - - 0 13"
FORK = {"move_number": 13, "side": "white", "move": "Ke2", "eval_before": 4.8, "eval_after": 0.1,
        "type": "blunder", "fen_before": FORK_FEN, "best_move": "Nc7+", "best_line": "Nc7+ Kd7 Nxa8"}
# 20.Ra8# was there; White played 20.Kf2.
MATE = {"move_number": 20, "side": "white", "move": "Kf2", "eval_before": 10000, "eval_after": 3.0,
        "type": "missed_mate", "fen_before": "6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 20", "best_move": "Ra8#"}
# Black to move: the white queen on d5 hangs to 31...Rxd5; Black played 31...Kf8.
HANGING = {"move_number": 31, "side": "black", "move": "Kf8", "eval_before": -6.0, "eval_after": 3.0,
           "type": "blunder", "fen_before": "3rk3/8/8/3Q4/8/8/8/4K3 b - - 0 31", "best_move": "Rxd5"}
PGN = '[White "Carlsen, M."]\n[Black "Student"]\n[Result "1-0"]\n\n1. e4 e5 1-0'


def test_good_input_is_typed_and_checked():
    s = build_review_moments({"critical_moments": [FORK, MATE, HANGING]}, pgn=PGN, game_id="g1")
    assert s["kind"] == "review_moments"
    assert s["game"] == {"white": "Carlsen, M.", "black": "Student", "result": "1-0", "id": "g1"}
    fork, mate, hanging = s["moments"]
    assert fork == {
        "ply": 25, "fen": chess.Board(FORK_FEN).fen(), "played": "Ke2", "best": "Nc7+", "best_uci": "b5c7",
        "motif": "fork", "question": "В партии было 13.Ke2. Найдите ход сильнее за белых.",
        "explanation": "Сильнее 13.Nc7+ — вилка. После 13.Ke2 оценка изменилась: +4.8 → +0.1.",
        "eval_before": 480, "eval_after": 10,
    }
    assert mate["motif"] == "mate" and mate["best_uci"] == "a1a8" and mate["ply"] == 39
    assert mate["question"] == "Белые могут поставить мат. Найдите ход!"
    assert "+мат → +3.0" in mate["explanation"]
    assert hanging["ply"] == 62 and hanging["motif"] == "hanging_piece" and hanging["best"] == "Rxd5"
    assert hanging["question"].endswith("за чёрных.") and "31...Kf8" in hanging["question"]


def test_fen_side_to_move_is_the_mover():
    s = build_review_moments({"critical_moments": [FORK, HANGING]})
    for m in s["moments"]:
        board = chess.Board(m["fen"])
        assert chess.Move.from_uci(m["best_uci"]) in board.legal_moves
        assert board.parse_san(m["played"]) in board.legal_moves


def test_english():
    m = build_review_moments({"moments": [FORK]}, language="en")["moments"][0]
    assert m["question"] == "The game went 13.Ke2. Find a stronger move for White."
    assert m["explanation"].startswith("Better was 13.Nc7+ — a fork.")


def test_no_pgn_gives_unknown_players():
    assert build_review_moments({"moments": [FORK]})["game"] == {"white": "?", "black": "?"}


@pytest.mark.parametrize("best", ["Qh5", "Nxa8", "e2e4", "b5b4", "zz"])
def test_illegal_best_move_is_dropped(best):
    # No queen; the rook is not in reach; no pawn; a knight does not move so; not a move.
    s = build_review_moments({"critical_moments": [{**FORK, "best_move": best}, HANGING]})
    assert [m["best"] for m in s["moments"]] == ["Rxd5"]


def test_uci_best_move_is_read():
    m = build_review_moments({"critical_moments": [{**FORK, "best_move": "b5c7"}]})["moments"][0]
    assert m["best"] == "Nc7+" and m["best_uci"] == "b5c7"


@pytest.mark.parametrize("bad", [
    {**FORK, "move": "Kxe8"},              # the played move is illegal
    {**FORK, "best_move": None},           # no better move to find
    {**FORK, "best_move": "Ke2"},          # the best move is the move played
    {**FORK, "side": "black"},             # the row and its position disagree on the mover
    {**FORK, "fen_before": "not a fen"},
    {**FORK, "fen_before": None},
    "a string row",
])
def test_bad_moment_is_dropped(bad):
    s = build_review_moments({"critical_moments": [bad, HANGING]})
    assert [m["best"] for m in s["moments"]] == ["Rxd5"]


@pytest.mark.parametrize("data", [
    None, "x", [], {}, {"critical_moments": []}, {"critical_moments": "x"}, {"moments": None},
    {"critical_moments": [{"move": "e4"}]},
])
def test_malformed_input_gives_none(data):
    assert build_review_moments(data) is None


def test_truncates_to_ten_in_game_order():
    rows = [{**FORK, "fen_before": FORK_FEN.replace(" 13", f" {n}"), "move_number": n} for n in range(40, 15, -1)]
    s = build_review_moments({"critical_moments": rows})
    assert len(s["moments"]) == MAX_MOMENTS == 10
    plies = [m["ply"] for m in s["moments"]]
    assert plies == sorted(plies) and plies[0] == (16 - 1) * 2 + 1


def test_side_filter():
    s = build_review_moments({"moments": [FORK, HANGING]}, side="black")
    assert [m["best"] for m in s["moments"]] == ["Rxd5"]
    assert build_review_moments({"moments": [FORK]}, side="black") is None


def test_no_motif_when_the_board_shows_none():
    quiet = {"move_number": 1, "side": "white", "move": "a3", "eval_before": 0.3, "eval_after": -1.5,
             "type": "mistake", "fen_before": chess.STARTING_FEN, "best_move": "e4"}
    m = build_review_moments({"moments": [quiet]})["moments"][0]
    assert "motif" not in m and m["explanation"].startswith("Сильнее 1.e4.")


def test_json_safe():
    s = build_review_moments({"critical_moments": [FORK, MATE, HANGING]}, pgn=PGN)
    assert json.loads(json.dumps(s, ensure_ascii=False)) == s


class TestThroughBuildSummary:
    def test_review_tools_give_review_moments(self):
        raw = json.dumps({"critical_moments": [FORK], "total_moves": 40})
        s = build_summary("find_critical_moments", {"pgn": PGN}, raw, language="ru")
        assert s["kind"] == "review_moments" and s["game"]["white"] == "Carlsen, M."
        raw = json.dumps({"moments": [FORK, HANGING], "note": "…"})
        s = build_summary("review_game", {"pgn": PGN, "side": "black"}, raw, language="en")
        assert [m["best"] for m in s["moments"]] == ["Rxd5"]

    def test_falls_back_to_critical_moments(self):
        # A moment with no better move: still a turning point for the P3a list.
        raw = json.dumps({"critical_moments": [{**FORK, "best_move": None}]})
        s = build_summary("find_critical_moments", {}, raw)
        assert s["kind"] == "critical_moments" and s["moments"][0]["san"] == "Ke2"
