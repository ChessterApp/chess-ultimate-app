"""Unit tests for find_critical_moments tool."""

import io
from unittest.mock import MagicMock

import pytest

from src.tools.critical_moments import find_critical_moments


def _make_mock_proc(eval_sequence):
    """Create a mock Stockfish process that returns sequential evaluations.

    eval_sequence: list of centipawn values (one per position).
    """
    call_count = [0]

    class MockStdout:
        def readline(self):
            idx = call_count[0]
            if idx >= len(eval_sequence) * 2:
                return ""
            if idx % 2 == 0:
                cp = eval_sequence[idx // 2]
                call_count[0] += 1
                return f"info depth 15 seldepth 20 multipv 1 score cp {cp} nodes 100 nps 100000 time 1 pv e2e4\n"
            else:
                call_count[0] += 1
                return "bestmove e2e4\n"

    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    mock_proc.stdout = MockStdout()
    mock_proc.stderr = io.StringIO("")
    mock_proc.returncode = 0
    mock_proc.wait = MagicMock(return_value=0)
    mock_proc.kill = MagicMock()
    return mock_proc


@pytest.mark.unit
def test_simple_game():
    """A short game produces result with total_moves."""
    pgn = "1. e4 e5 2. Nf3 Nc6 1-0"
    # 5 positions (initial + 4 moves), all eval ~35cp (stable)
    mock_proc = _make_mock_proc([35, 35, 35, 35, 35])
    result = find_critical_moments(pgn, _proc=mock_proc)

    assert "error" not in result
    assert result["total_moves"] == 4


@pytest.mark.unit
def test_detects_blunder():
    """A big eval swing is detected as a critical moment."""
    pgn = "1. e4 e5 2. Nf3 Nc6 1-0"
    # Position evals: 35, 35, -300, -300, -300 (big drop after move 2)
    mock_proc = _make_mock_proc([35, 35, -300, -300, -300])
    result = find_critical_moments(pgn, threshold=1.5, _proc=mock_proc)

    assert len(result["critical_moments"]) >= 1


@pytest.mark.unit
def test_no_critical_moments_in_stable_game():
    """A stable game has no critical moments."""
    pgn = "1. e4 e5 2. Nf3 Nc6 1-0"
    # All evals close together (within threshold)
    mock_proc = _make_mock_proc([35, 30, 32, 28, 35])
    result = find_critical_moments(pgn, threshold=1.5, _proc=mock_proc)

    assert result["critical_moments"] == []


@pytest.mark.unit
def test_invalid_pgn():
    """Invalid PGN returns error."""
    result = find_critical_moments("not a valid pgn")
    assert "error" in result


@pytest.mark.unit
def test_empty_pgn():
    """Empty PGN returns error."""
    result = find_critical_moments("")
    assert "error" in result


@pytest.mark.unit
def test_critical_moment_fields():
    """Critical moment entries have expected fields."""
    pgn = "1. e4 e5 2. Nf3 Nc6 1-0"
    mock_proc = _make_mock_proc([35, 35, -500, -500, -500])
    result = find_critical_moments(pgn, threshold=1.5, _proc=mock_proc)

    for moment in result["critical_moments"]:
        assert "move_number" in moment
        assert "side" in moment
        assert "move" in moment
        assert "eval_before" in moment
        assert "eval_after" in moment
        assert "type" in moment
