"""Typed tool_result summaries for the coach's rich cards (src/tool_summaries.py, P3a)."""

import json

import pytest

from src.tool_summaries import (
    MAX_ENGINE_LINES,
    MAX_GAMES,
    MAX_LINE_PLIES,
    MAX_MOMENTS,
    build_summary,
)

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"

pytestmark = pytest.mark.unit


class TestEngineLine:
    def test_analyze_position(self):
        raw = json.dumps({
            "evaluation": 0.31, "best_move": "e2e4",
            "lines": [
                {"pv": "e2e4 e7e5 g1f3", "score": 0.31, "depth": 18},
                {"pv": "d2d4 d7d5", "score": 0.25, "depth": 18},
            ],
        })
        s = build_summary("analyze_position", {"fen": START}, raw)
        assert s == {
            "kind": "engine_line", "fen": START, "eval_cp": 31, "depth": 18,
            "lines": [
                {"san": ["e4", "e5", "Nf3"], "eval_cp": 31},
                {"san": ["d4", "d5"], "eval_cp": 25},
            ],
        }

    def test_scores_turn_to_whites_side(self):
        # Black to move and better for Black: the engine says +0.5, White's side −50.
        raw = json.dumps({"lines": [{"pv": "e7e5", "score": 0.5, "depth": 12}]})
        s = build_summary("analyze_position", {"fen": AFTER_E4}, raw)
        assert s["eval_cp"] == -50 and s["lines"][0]["san"] == ["e5"]

    def test_mate(self):
        fen = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"
        raw = json.dumps({"lines": [{"pv": "a1a8", "score": 10000, "mate_in": 1, "depth": 5}]})
        s = build_summary("analyze_position", {"fen": fen}, raw)
        assert s["mate"] == 1 and "eval_cp" not in s
        assert s["lines"][0] == {"san": ["Ra8#"], "mate": 1}

    def test_compare_variations(self):
        raw = json.dumps({"fen": START, "depth": 14, "variations": [
            {"moves": "e2e4 e7e5", "score": 0.3},
            {"moves": "g1f3", "score": 0.2},
        ]})
        s = build_summary("compare_variations", {}, raw)
        assert s["depth"] == 14 and [l["san"] for l in s["lines"]] == [["e4", "e5"], ["Nf3"]]

    def test_truncates_lines_and_plies(self):
        pv = "g1f3 g8f6 f3g1 f6g8 " * 4
        raw = json.dumps({"lines": [{"pv": pv, "score": 0.1}] * 6})
        s = build_summary("analyze_position", {"fen": START}, raw)
        assert len(s["lines"]) == MAX_ENGINE_LINES
        assert all(len(l["san"]) == MAX_LINE_PLIES for l in s["lines"])

    def test_stops_at_an_illegal_move(self):
        raw = json.dumps({"lines": [{"pv": "e2e4 e2e4", "score": 0.3}]})
        s = build_summary("analyze_position", {"fen": START}, raw)
        assert s["lines"][0]["san"] == ["e4"]

    @pytest.mark.parametrize("args,raw", [
        ({"fen": START}, '{"error": "Invalid FEN"}'),
        ({"fen": "not a fen"}, json.dumps({"lines": [{"pv": "e2e4", "score": 0.3}]})),
        ({}, json.dumps({"lines": [{"pv": "e2e4", "score": 0.3}]})),
        ({"fen": START}, json.dumps({"lines": [{"pv": "z9z9", "score": 0.3}]})),
        ({"fen": START}, json.dumps({"lines": [{"pv": "e2e4", "score": "x"}]})),
        ({"fen": START}, "not json"),
        ({"fen": START}, json.dumps([1, 2])),
        ("junk", None),
    ])
    def test_malformed(self, args, raw):
        assert build_summary("analyze_position", args, raw) is None


class TestGameList:
    def test_twic_search(self):
        rows = [{"id": 7, "white_name": "Kasparov, G", "black_name": "Topalov, V", "result": "1-0",
                 "date": "1999.01.20", "eco": "B07", "opening": "Pirc", "event": "Wijk",
                 "white_elo": 2812, "black_elo": 2700}]
        s = build_summary("search_master_games", {}, json.dumps(rows))
        assert s == {"kind": "game_list", "games": [{
            "id": 7, "white": "Kasparov, G", "black": "Topalov, V", "result": "1-0",
            "eco": "B07", "year": 1999, "white_elo": 2812, "black_elo": 2700,
        }]}

    def test_by_position_and_user_games(self):
        raw = json.dumps({"fen": START, "total": 1, "games": [
            {"id": 3, "white": "A", "black": "B", "result": "0-1", "date": "2001-02-03", "white_elo": None},
        ]})
        s = build_summary("find_games_by_position", {}, raw)
        assert s["games"] == [{"id": 3, "white": "A", "black": "B", "result": "0-1", "year": 2001}]
        user = json.dumps({"user_id": "u", "count": 1, "games": [
            {"id": "g-1", "white": "me", "black": "you", "pgn": '[Result "1-0"]\n[ECO "C20"]\n\n1. e4 1-0'},
        ]})
        g = build_summary("get_user_games", {}, user)["games"][0]
        assert g == {"id": "g-1", "white": "me", "black": "you", "result": "1-0", "eco": "C20"}

    def test_import_ids_match_game_results(self):
        from src.middleware.response_envelope import extract_game_results

        raw = json.dumps({"imported": 2, "source": "lichess", "last_games": [
            {"pgn": "1. e4 *", "white": "a", "black": "b", "result": "*", "date": "2026.10.01"},
            {"pgn": "1. d4 *", "white": "c", "black": "d", "result": "1-0", "date": ""},
        ]})
        s = build_summary("lichess_game_import", {}, raw)
        assert [g["id"] for g in s["games"]] == [c["id"] for c in extract_game_results([raw])]

    def test_famous_game(self):
        pgn = '[White "Morphy"]\n[Black "Duke Karl"]\n[Result "1-0"]\n[Date "1858.??.??"]\n\n1. e4 e5 1-0'
        raw = json.dumps({"found": True, "name": "Opera", "board_actions": [{"type": "load_pgn", "pgn": pgn}]})
        s = build_summary("famous_game", {}, raw)
        assert s["games"] == [{"white": "Morphy", "black": "Duke Karl", "result": "1-0", "year": 1858}]
        assert build_summary("famous_game", {}, json.dumps({"found": False})) is None

    def test_truncates(self):
        rows = [{"id": i, "white_name": "W", "black_name": "B", "result": "1-0"} for i in range(30)]
        assert len(build_summary("search_master_games", {}, json.dumps(rows))["games"]) == MAX_GAMES

    @pytest.mark.parametrize("raw", [
        "[]", '{"error": "timeout", "games": []}', json.dumps([{"id": 1}]), json.dumps({"games": "x"}), "{",
    ])
    def test_malformed(self, raw):
        assert build_summary("search_master_games", {}, raw) is None


class TestOpening:
    def test_identify(self):
        raw = json.dumps({"eco": "B20", "name": "Sicilian Defense", "book_line": "1. e4 c5",
                          "book_plies": 2, "out_of_book_after": 2, "total_plies": 4})
        assert build_summary("identify_opening", {}, raw) == {
            "kind": "opening", "name": "Sicilian Defense", "eco": "B20", "moves_san": ["e4", "c5"],
        }

    def test_stats(self):
        raw = json.dumps({"eco": "C65", "name": "Ruy Lopez: Berlin", "main_line": "1. e4 e5 2. Nf3 Nc6 3. Bb5 Nf6",
                          "games_count": 1200, "white_win_pct": 35.5, "draw_pct": 45.0, "black_win_pct": 19.5})
        s = build_summary("get_opening_stats", {}, raw)
        assert s["stats"] == {"white": 35.5, "draw": 45.0, "black": 19.5, "games": 1200}
        assert s["moves_san"][-1] == "Nf6"

    def test_lookup_and_no_stats(self):
        raw = json.dumps({"found": True, "name": "Italian Game", "eco": "C50", "line": "1. e4 e5 2. Nf3 Nc6 3. Bc4"})
        s = build_summary("lookup_opening", {}, raw)
        assert s["name"] == "Italian Game" and "stats" not in s and len(s["moves_san"]) == 5

    def test_truncates_long_lines(self):
        line = " ".join(f"{i}. Nf3 Nf6 {i}. Ng1 Ng8" for i in range(1, 20))
        s = build_summary("identify_opening", {}, json.dumps({"eco": "A04", "name": "x", "book_line": line}))
        assert len(s["moves_san"]) == 20

    @pytest.mark.parametrize("raw", [
        '{"found": false}', '{"error": "No book line"}', json.dumps({"name": "x"}), "[]", "nope",
    ])
    def test_malformed(self, raw):
        assert build_summary("lookup_opening", {}, raw) is None


class TestPuzzle:
    def test_puzzle_on_board(self):
        raw = json.dumps({"count": 2, "on_board": "b2", "puzzles": [
            {"puzzle_id": "a1", "fen": START, "rating": 1200, "themes": ["fork"]},
            {"puzzle_id": "b2", "fen": AFTER_E4, "rating": 1500, "themes": [f"t{i}" for i in range(9)], "solution": ["e7e5"]},
        ]})
        s = build_summary("get_puzzle", {}, raw)
        assert s == {"kind": "puzzle", "puzzle_id": "b2", "fen": AFTER_E4, "rating": 1500,
                     "themes": ["t0", "t1", "t2", "t3", "t4", "t5"], "queued": 1}  # one more lined up (20.10)

    def test_site_puzzle_without_rating(self):
        raw = json.dumps({"rating": None, "on_board": 42, "puzzles": [{"puzzle_id": 42, "fen": START}]})
        assert build_summary("get_puzzle", {}, raw) == {"kind": "puzzle", "puzzle_id": "42", "fen": START}

    @pytest.mark.parametrize("raw", [
        '{"error": "No puzzle matched."}', '{"puzzles": []}',
        json.dumps({"puzzles": [{"puzzle_id": "x", "fen": "bad"}]}),
        json.dumps({"puzzles": [{"fen": START}]}),
    ])
    def test_malformed(self, raw):
        assert build_summary("get_puzzle", {}, raw) is None


class TestCriticalMoments:
    MOMENT = {"move_number": 13, "side": "black", "move": "Qxb2", "eval_before": 0.4, "eval_after": -2.6,
              "eval_change": -3.0, "type": "blunder", "fen_before": START, "best_move": "O-O"}

    def test_find_critical_moments(self):
        raw = json.dumps({"total_moves": 60, "evals_from": "white", "critical_moments": [
            self.MOMENT, {**self.MOMENT, "move_number": 20, "side": "white", "eval_after": -10000, "type": "missed_mate"},
        ]})
        s = build_summary("find_critical_moments", {}, raw)
        assert s["moments"][0] == {"ply": 26, "san": "Qxb2", "eval_before": 40, "eval_after": -260, "label": "blunder"}
        assert s["moments"][1]["ply"] == 39 and s["moments"][1]["eval_after"] == -10000

    def test_review_game(self):
        raw = json.dumps({"moments": [self.MOMENT], "total_moves": 40, "note": "…"})
        assert build_summary("review_game", {}, raw)["moments"][0]["san"] == "Qxb2"

    def test_truncates(self):
        raw = json.dumps({"critical_moments": [self.MOMENT] * 25})
        assert len(build_summary("find_critical_moments", {}, raw)["moments"]) == MAX_MOMENTS

    @pytest.mark.parametrize("raw", [
        '{"error": "Could not parse PGN."}', '{"critical_moments": []}',
        json.dumps({"critical_moments": [{"move": "e4"}]}), json.dumps({"moments": "x"}),
    ])
    def test_malformed(self, raw):
        assert build_summary("find_critical_moments", {}, raw) is None


def test_unknown_tool_and_never_raises():
    assert build_summary("board_control", {}, '{"type": "set_position"}') is None
    assert build_summary("check_moves", {"fen": START}, '{"fen": "x", "results": []}') is None
    assert build_summary("analyze_position", object(), object()) is None


def test_summaries_are_json_safe():
    raw = json.dumps({"lines": [{"pv": "e2e4", "score": 0.3, "depth": 10}]})
    s = build_summary("analyze_position", {"fen": START}, raw)
    assert json.loads(json.dumps(s)) == s
