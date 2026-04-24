"""Unit tests for compare_variations tool."""

import io
from unittest.mock import MagicMock, patch

import chess
import pytest

from src.tools.compare_variations import compare_variations

MULTI_PV_OUTPUT = (
    "info depth 20 seldepth 30 multipv 1 score cp 35 nodes 1234567 nps 2000000 "
    "time 617 pv e2e4 e7e5 g1f3 b8c6 f1b5\n"
    "info depth 20 seldepth 28 multipv 2 score cp 28 nodes 1234567 nps 2000000 "
    "time 617 pv d2d4 d7d5 c2c4 e7e6\n"
    "info depth 20 seldepth 26 multipv 3 score cp 20 nodes 1234567 nps 2000000 "
    "time 617 pv g1f3 d7d5 d2d4\n"
    "bestmove e2e4 ponder e7e5\n"
)


def _mock_popen(output):
    def make(*args, **kwargs):
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = io.StringIO(output)
        mock_proc.stderr = io.StringIO("")
        mock_proc.returncode = 0
        mock_proc.wait = MagicMock(return_value=0)
        mock_proc.kill = MagicMock()
        return mock_proc
    return make


@pytest.mark.unit
def test_compare_three_lines():
    """Comparing 3 lines returns 3 variations."""
    with patch("subprocess.Popen", side_effect=_mock_popen(MULTI_PV_OUTPUT)):
        result = compare_variations(chess.STARTING_FEN, num_lines=3)

    assert "error" not in result
    assert len(result["variations"]) == 3
    assert result["depth"] == 20


@pytest.mark.unit
def test_variation_fields():
    """Each variation has moves and score fields."""
    with patch("subprocess.Popen", side_effect=_mock_popen(MULTI_PV_OUTPUT)):
        result = compare_variations(chess.STARTING_FEN, num_lines=3)

    for var in result["variations"]:
        assert "moves" in var
        assert "score" in var


@pytest.mark.unit
def test_invalid_fen():
    """Invalid FEN returns error without calling Stockfish."""
    result = compare_variations("not a valid fen")
    assert "error" in result


@pytest.mark.unit
def test_num_lines_clamped():
    """num_lines is clamped between 1 and 10."""
    with patch("subprocess.Popen", side_effect=_mock_popen(MULTI_PV_OUTPUT)):
        result = compare_variations(chess.STARTING_FEN, num_lines=100)

    # Should not crash, num_lines clamped to 10
    assert "error" not in result


@pytest.mark.unit
def test_custom_depth():
    """Custom depth is passed through."""
    with patch("subprocess.Popen", side_effect=_mock_popen(MULTI_PV_OUTPUT)):
        result = compare_variations(chess.STARTING_FEN, depth=15)

    assert result["depth"] == 15
