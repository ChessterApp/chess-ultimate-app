"""Unit tests for Tool 5: analyze_position."""

import io
import subprocess
from unittest.mock import MagicMock, patch

import chess
import pytest

from src.tools.stockfish import analyze_position

MULTI_PV_OUTPUT = (
    "info depth 20 seldepth 30 multipv 1 score cp 35 nodes 1234567 nps 2000000 "
    "time 617 pv e2e4 e7e5 g1f3 b8c6 f1b5\n"
    "info depth 20 seldepth 28 multipv 2 score cp 28 nodes 1234567 nps 2000000 "
    "time 617 pv d2d4 d7d5 c2c4 e7e6\n"
    "info depth 20 seldepth 26 multipv 3 score cp 20 nodes 1234567 nps 2000000 "
    "time 617 pv g1f3 d7d5 d2d4\n"
    "bestmove e2e4 ponder e7e5\n"
)

MATE_OUTPUT = (
    "info depth 20 seldepth 2 multipv 1 score mate 1 nodes 100 nps 100000 "
    "time 1 pv d1h5\n"
    "bestmove d1h5\n"
)


def _mock_popen(output):
    """Create a mock Popen that returns canned output."""
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
def test_starting_position(mock_stockfish):
    """Starting position returns evaluation and best move."""
    result = analyze_position(chess.STARTING_FEN)
    assert "evaluation" in result
    assert "best_move" in result
    assert "lines" in result
    assert result["best_move"] == "e2e4"
    assert isinstance(result["evaluation"], float)


@pytest.mark.unit
def test_mate_in_one():
    """Mate-in-1 position returns mate score."""
    with patch("subprocess.Popen", side_effect=_mock_popen(MATE_OUTPUT)):
        # Scholar's mate position: Qh5 is mate
        fen = "r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4"
        result = analyze_position(fen)

    assert result["best_move"] == "d1h5"
    # Mate score should be very high
    assert result["lines"][0]["score"] == 10000


@pytest.mark.unit
def test_custom_depth():
    """Custom depth parameter is passed to Stockfish."""
    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    mock_proc.stdout = io.StringIO(MULTI_PV_OUTPUT)
    mock_proc.stderr = io.StringIO("")
    mock_proc.returncode = 0
    mock_proc.wait = MagicMock(return_value=0)
    mock_proc.kill = MagicMock()

    with patch("subprocess.Popen", return_value=mock_proc):
        analyze_position(chess.STARTING_FEN, depth=15)

    # Check that "go depth 15" was written to stdin
    write_calls = mock_proc.stdin.write.call_args_list
    written = "".join(str(c[0][0]) for c in write_calls)
    assert "go depth 15" in written


@pytest.mark.unit
def test_multipv():
    """MultiPV parameter returns multiple lines."""
    with patch("subprocess.Popen", side_effect=_mock_popen(MULTI_PV_OUTPUT)):
        result = analyze_position(chess.STARTING_FEN, multipv=3)

    assert len(result["lines"]) == 3
    for line in result["lines"]:
        assert "pv" in line
        assert "score" in line
        assert "depth" in line


@pytest.mark.unit
def test_invalid_fen():
    """Invalid FEN returns error without calling Stockfish."""
    result = analyze_position("not a valid fen string")
    assert "error" in result
    assert "Invalid FEN" in result["error"]


@pytest.mark.unit
def test_timeout():
    """Stockfish timeout (hanging stdout.readline) returns error."""
    def make_hanging_popen(*args, **kwargs):
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        # Simulate hanging by returning empty string (EOF) immediately
        # after some non-bestmove lines, causing the while loop timeout
        mock_proc.stdout = io.StringIO("info string NNUE enabled\n")
        mock_proc.stderr = io.StringIO("")
        mock_proc.returncode = 0
        mock_proc.wait = MagicMock(return_value=0)
        mock_proc.kill = MagicMock()
        return mock_proc

    with patch("subprocess.Popen", side_effect=make_hanging_popen):
        result = analyze_position(chess.STARTING_FEN, timeout=1)

    # When stdout reaches EOF without bestmove, lines will be empty
    assert result["best_move"] == ""
    assert result["lines"] == []


@pytest.mark.unit
def test_fen_validation():
    """Various invalid FEN strings are rejected."""
    invalid_fens = [
        "",
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP",  # incomplete
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR x KQkq - 0 1",  # bad turn
    ]
    for fen in invalid_fens:
        result = analyze_position(fen)
        assert "error" in result, f"Expected error for FEN: {fen}"
