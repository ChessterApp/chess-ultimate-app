"""Unit tests for find_critical_moments tool."""

import io
from unittest.mock import MagicMock

import pytest

from src.tools.critical_moments import find_critical_moments


def _make_mock_proc(eval_sequence):
    """Create a mock Stockfish process that returns sequential evaluations.

    eval_sequence: one value per position of a game from the initial position,
    from White's side — centipawns, or "M3" / "M-2" for a mate (White mates /
    gets mated). The mock reports them the way UCI does: from the side to move.
    """
    call_count = [0]

    def _uci_score(i):
        value = eval_sequence[i]
        white_to_move = i % 2 == 0
        if isinstance(value, str) and value.startswith("M"):
            n = int(value[1:])
            return f"mate {n if white_to_move else -n}"
        return f"cp {value if white_to_move else -value}"

    class MockStdout:
        def readline(self):
            idx = call_count[0]
            if idx >= len(eval_sequence) * 2:
                return ""
            if idx % 2 == 0:
                score = _uci_score(idx // 2)
                call_count[0] += 1
                return f"info depth 12 seldepth 20 multipv 1 score {score} nodes 100 nps 100000 time 1 pv e2e4\n"
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
    # Position evals: 35, 35, 35, -300, -300 (White's second move drops the eval)
    mock_proc = _make_mock_proc([35, 35, 35, -300, -300])
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
    mock_proc = _make_mock_proc([35, 35, 35, -500, -500])
    result = find_critical_moments(pgn, threshold=1.5, _proc=mock_proc)

    assert result["critical_moments"]
    for moment in result["critical_moments"]:
        assert "move_number" in moment
        assert "side" in moment
        assert "move" in moment
        assert "eval_before" in moment
        assert "eval_after" in moment
        assert "type" in moment


@pytest.mark.unit
def test_blunder_is_on_the_mover_who_lost_the_eval():
    """White's 2. Nf3 drops from +0.35 to -3.00: that move, and only it, is flagged."""
    pgn = "1. e4 e5 2. Nf3 Nc6 1-0"
    mock_proc = _make_mock_proc([35, 35, 35, -300, -300])
    result = find_critical_moments(pgn, threshold=1.5, _proc=mock_proc)

    assert result["evals_from"] == "white"
    [moment] = result["critical_moments"]
    assert (moment["move_number"], moment["side"], moment["move"]) == (2, "white", "Nf3")
    assert moment["type"] == "blunder"
    assert (moment["eval_before"], moment["eval_after"]) == (0.35, -3.0)


@pytest.mark.unit
def test_a_steadily_won_game_is_not_all_blunders():
    """Regression: raw side-to-move scores flip sign every ply, and a +5 game came back
    with every move flagged (Morphy's Opera Game: 28 of 33)."""
    pgn = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 1-0"
    mock_proc = _make_mock_proc([500, 500, 510, 490, 500, 505, 500])
    result = find_critical_moments(pgn, threshold=1.5, _proc=mock_proc)

    assert result["critical_moments"] == []


@pytest.mark.unit
def test_walking_into_mate_and_the_mate_itself():
    """Fool's mate: 2. g4?? allows mate in one; the mating move is not a mistake."""
    pgn = "1. f3 e5 2. g4 Qh4# 0-1"
    # The final position is checkmate: evaluated from the board, not the engine.
    mock_proc = _make_mock_proc([20, -60, -70, "M-1"])
    result = find_critical_moments(pgn, threshold=1.5, _proc=mock_proc)

    [moment] = result["critical_moments"]
    assert (moment["side"], moment["move"], moment["type"]) == ("white", "g4", "blunder")
    assert moment["eval_after"] == -10000.0


@pytest.mark.unit
def test_letting_a_forced_mate_go_is_a_missed_mate():
    pgn = "1. e4 e5 2. Nf3 Nc6 1-0"
    # White has a forced mate from move 1; 2. Nf3 lets it go (still +1.5).
    mock_proc = _make_mock_proc([35, "M5", "M4", 150, 150])
    result = find_critical_moments(pgn, threshold=1.5, _proc=mock_proc)

    [moment] = result["critical_moments"]
    assert (moment["side"], moment["move"], moment["type"]) == ("white", "Nf3", "missed_mate")
