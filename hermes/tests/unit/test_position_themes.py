"""Unit tests for score_position_themes tool."""

import chess
import pytest

from src.tools.position_themes import score_position_themes


@pytest.mark.unit
def test_starting_position():
    """Starting position has equal material and balanced scores."""
    result = score_position_themes(chess.STARTING_FEN)
    assert "error" not in result
    assert result["material"]["balance"] == 0
    assert result["material"]["white_material"] == result["material"]["black_material"]


@pytest.mark.unit
def test_material_imbalance():
    """Position with material imbalance is detected."""
    # White missing a queen
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNB1KBNR w KQkq - 0 1"
    result = score_position_themes(fen)
    assert result["material"]["balance"] < 0  # White is down material


@pytest.mark.unit
def test_mobility_scores():
    """Mobility scores are returned for both sides."""
    result = score_position_themes(chess.STARTING_FEN)
    assert "white_moves" in result["mobility"]
    assert "black_moves" in result["mobility"]
    assert result["mobility"]["white_moves"] == 20  # Standard opening moves


@pytest.mark.unit
def test_space_control():
    """Space control scores include center and extended center."""
    result = score_position_themes(chess.STARTING_FEN)
    assert "white_center" in result["space_control"]
    assert "black_center" in result["space_control"]
    assert "white_extended_center" in result["space_control"]


@pytest.mark.unit
def test_king_safety():
    """King safety scores include pawn shield and open files."""
    result = score_position_themes(chess.STARTING_FEN)
    assert "white_pawn_shield" in result["king_safety"]
    assert "white_open_files_near_king" in result["king_safety"]
    assert "black_pawn_shield" in result["king_safety"]


@pytest.mark.unit
def test_invalid_fen():
    """Invalid FEN returns error."""
    result = score_position_themes("not a fen")
    assert "error" in result


@pytest.mark.unit
def test_endgame_position():
    """Endgame position has correct material count."""
    # K+R vs K
    fen = "8/8/8/4k3/8/8/8/4K2R w - - 0 1"
    result = score_position_themes(fen)
    assert result["material"]["white_material"] == 5  # Rook only
    assert result["material"]["black_material"] == 0
    assert result["material"]["balance"] == 5
