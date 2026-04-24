"""Unit tests for game results extraction from tool output."""

import json

import pytest

from src.middleware.response_envelope import extract_game_results, wrap_response


class TestExtractGameResults:
    """Tests for extract_game_results()."""

    def test_empty_tool_results(self):
        assert extract_game_results([]) == []
        assert extract_game_results(None) == []

    def test_no_game_results_in_tool_output(self):
        results = ['{"type": "set_fen", "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"}']
        assert extract_game_results(results) == []

    def test_valid_game_results_extracted(self):
        games = [
            {
                "id": 42,
                "white_name": "Carlsen, Magnus",
                "black_name": "Nepomniachtchi, Ian",
                "result": "1-0",
                "date": "2024.01.15",
                "eco": "C50",
                "opening": "Italian Game",
                "event": "Candidates 2024",
                "white_elo": 2830,
                "black_elo": 2770,
            },
            {
                "id": 43,
                "white_name": "Sindarov, Javokhir",
                "black_name": "Gukesh, D",
                "result": "0-1",
                "date": "2024.01.16",
                "eco": "B90",
                "opening": "Sicilian Najdorf",
                "event": "Candidates 2024",
                "white_elo": 2700,
                "black_elo": 2750,
            },
        ]
        results = [json.dumps(games)]
        extracted = extract_game_results(results)
        assert len(extracted) == 2
        assert extracted[0]["id"] == 42
        assert extracted[0]["white_name"] == "Carlsen, Magnus"
        assert extracted[1]["result"] == "0-1"

    def test_non_string_results_skipped(self):
        assert extract_game_results([123, None, True]) == []

    def test_invalid_json_skipped(self):
        assert extract_game_results(["not json at all"]) == []

    def test_list_without_required_keys_ignored(self):
        results = [json.dumps([{"foo": "bar", "baz": 1}])]
        assert extract_game_results(results) == []

    def test_empty_list_ignored(self):
        results = [json.dumps([])]
        assert extract_game_results(results) == []

    def test_single_dict_not_array_ignored(self):
        result = json.dumps({"id": 1, "white_name": "A", "black_name": "B"})
        assert extract_game_results([result]) == []

    def test_mixed_tool_results_finds_games(self):
        """Game results found even when mixed with other tool output."""
        board_action = json.dumps({"type": "set_fen", "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"})
        games = [{"id": 1, "white_name": "A", "black_name": "B", "result": "1-0", "date": "2024", "eco": "C50", "opening": "x", "event": "y", "white_elo": 2500, "black_elo": 2400}]
        results = [board_action, json.dumps(games)]
        extracted = extract_game_results(results)
        assert len(extracted) == 1
        assert extracted[0]["white_name"] == "A"


class TestWrapResponseWithGameResults:
    """Tests for wrap_response() including game_results."""

    def test_no_tool_results_gives_empty_game_results(self):
        envelope = wrap_response("Hello")
        assert envelope["game_results"] == []

    def test_game_results_included_in_envelope(self):
        games = [
            {"id": 1, "white_name": "A", "black_name": "B", "result": "1-0", "date": "2024", "eco": "C50", "opening": "x", "event": "y", "white_elo": 2500, "black_elo": 2400}
        ]
        envelope = wrap_response("Found 1 game.", tool_results=[json.dumps(games)])
        assert envelope["message"] == "Found 1 game."
        assert envelope["board_actions"] == []
        assert len(envelope["game_results"]) == 1
        assert envelope["game_results"][0]["id"] == 1

    def test_both_board_actions_and_game_results(self):
        """Board actions and game results coexist in the same envelope."""
        board_action = json.dumps({"type": "set_fen", "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"})
        games = [{"id": 5, "white_name": "X", "black_name": "Y", "result": "1/2-1/2", "date": "2024", "eco": "D10", "opening": "z", "event": "w", "white_elo": 2600, "black_elo": 2550}]
        envelope = wrap_response("Here are the results.", tool_results=[board_action, json.dumps(games)])
        assert len(envelope["board_actions"]) == 1
        assert len(envelope["game_results"]) == 1
