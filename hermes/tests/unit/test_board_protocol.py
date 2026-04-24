"""Unit tests for board protocol Pydantic models."""

import chess
import pytest

from src.board_protocol import (
    ActionType,
    Arrow,
    ClearBoard,
    DrawArrows,
    FlipBoard,
    HighlightSquares,
    LoadPgn,
    Navigate,
    NavigateDirection,
    ResponseEnvelope,
    SetFen,
    SetPuzzle,
    parse_pgn_moves,
    validate_fen,
)


@pytest.mark.unit
class TestFenValidation:
    def test_valid_starting_fen(self):
        result = validate_fen(chess.STARTING_FEN)
        assert result == chess.STARTING_FEN

    def test_valid_custom_fen(self):
        fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        result = validate_fen(fen)
        assert "rnbqkbnr" in result

    def test_invalid_fen_raises(self):
        with pytest.raises(ValueError, match="Invalid FEN"):
            validate_fen("not a fen string at all")

    def test_empty_fen_raises(self):
        with pytest.raises(ValueError, match="Invalid FEN"):
            validate_fen("")


@pytest.mark.unit
class TestPgnParsing:
    def test_parse_simple_pgn(self):
        pgn = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *"
        moves = parse_pgn_moves(pgn)
        assert moves == ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6"]

    def test_parse_pgn_with_result(self):
        pgn = "1. e4 e5 2. Nf3 Nc6 1-0"
        moves = parse_pgn_moves(pgn)
        assert moves == ["e4", "e5", "Nf3", "Nc6"]

    def test_invalid_pgn_raises(self):
        with pytest.raises(ValueError, match="Could not parse PGN"):
            parse_pgn_moves("")


@pytest.mark.unit
class TestSetFen:
    def test_valid_fen(self):
        action = SetFen(fen=chess.STARTING_FEN)
        assert action.action == ActionType.SET_FEN
        assert action.fen == chess.STARTING_FEN

    def test_invalid_fen_rejected(self):
        with pytest.raises(Exception):
            SetFen(fen="garbage")


@pytest.mark.unit
class TestLoadPgn:
    def test_valid_pgn(self):
        pgn = "1. e4 e5 2. Nf3 Nc6 *"
        action = LoadPgn(pgn=pgn)
        assert action.action == ActionType.LOAD_PGN
        assert action.moves == ["e4", "e5", "Nf3", "Nc6"]

    def test_invalid_pgn_rejected(self):
        with pytest.raises(Exception):
            LoadPgn(pgn="")


@pytest.mark.unit
class TestArrowValidation:
    def test_valid_arrow(self):
        arrow = Arrow(**{"from": "e2", "to": "e4"})
        assert arrow.from_sq == "e2"
        assert arrow.to_sq == "e4"
        assert arrow.color == "green"

    def test_invalid_square_rejected(self):
        with pytest.raises(Exception, match="Invalid square"):
            Arrow(**{"from": "z9", "to": "e4"})

    def test_case_insensitive(self):
        arrow = Arrow(**{"from": "E2", "to": "E4"})
        assert arrow.from_sq == "e2"
        assert arrow.to_sq == "e4"


@pytest.mark.unit
class TestHighlightSquares:
    def test_valid_squares(self):
        action = HighlightSquares(squares=["e4", "d5", "c6"])
        assert action.squares == ["e4", "d5", "c6"]
        assert action.color == "yellow"

    def test_invalid_square_rejected(self):
        with pytest.raises(Exception, match="Invalid square"):
            HighlightSquares(squares=["e4", "j9"])


@pytest.mark.unit
class TestSetPuzzle:
    def test_puzzle_with_solution(self):
        fen = "8/8/8/4k3/8/8/8/4K2R w - - 0 1"
        action = SetPuzzle(fen=fen, solution=["Rh5+", "Kd4"])
        assert action.action == ActionType.SET_PUZZLE
        assert action.solution == ["Rh5+", "Kd4"]


@pytest.mark.unit
class TestNavigateFlipClear:
    def test_navigate(self):
        action = Navigate(direction=NavigateDirection.NEXT)
        assert action.action == ActionType.NAVIGATE

    def test_flip(self):
        action = FlipBoard()
        assert action.action == ActionType.FLIP_BOARD

    def test_clear(self):
        action = ClearBoard()
        assert action.action == ActionType.CLEAR_BOARD


@pytest.mark.unit
class TestResponseEnvelope:
    def test_text_only_envelope(self):
        env = ResponseEnvelope(message="Hello!")
        d = env.model_dump()
        assert d["message"] == "Hello!"
        assert d["board_actions"] == []

    def test_envelope_with_actions(self):
        env = ResponseEnvelope(
            message="Here's the position.",
            board_actions=[SetFen(fen=chess.STARTING_FEN)],
        )
        d = env.model_dump()
        assert d["message"] == "Here's the position."
        assert len(d["board_actions"]) == 1
        assert d["board_actions"][0]["action"] == "set_fen"
