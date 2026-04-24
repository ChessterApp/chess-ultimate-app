"""Integration tests for Stockfish — requires the stockfish binary."""

import shutil

import chess
import pytest

from src.tools.stockfish import analyze_position


@pytest.mark.integration
def test_binary_exists():
    """Stockfish binary is installed and accessible."""
    assert shutil.which("stockfish") is not None


@pytest.mark.integration
def test_live_analysis():
    """Live Stockfish analysis on starting position returns valid results."""
    result = analyze_position(chess.STARTING_FEN, depth=10, multipv=1)

    assert "error" not in result
    assert "evaluation" in result
    assert "best_move" in result
    assert "lines" in result
    assert len(result["lines"]) >= 1
    assert result["best_move"]  # non-empty


@pytest.mark.integration
def test_performance():
    """Depth-10 analysis completes in under 10 seconds."""
    import time
    start = time.time()
    result = analyze_position(chess.STARTING_FEN, depth=10, multipv=1)
    elapsed = time.time() - start

    assert "error" not in result
    assert elapsed < 10, f"Analysis took {elapsed:.1f}s, expected <10s"
