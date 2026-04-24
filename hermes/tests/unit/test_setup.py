import os
import shutil

import pytest


@pytest.mark.unit
def test_hermes_importable():
    from run_agent import AIAgent
    assert AIAgent is not None


@pytest.mark.unit
def test_python_chess_importable():
    import chess
    assert chess.Board() is not None


@pytest.mark.unit
def test_stockfish_binary_exists():
    assert shutil.which("stockfish") is not None


@pytest.mark.unit
def test_twic_db_exists():
    assert os.path.exists("/root/chess-app/backend/data/twic/chess_games.db")


@pytest.mark.unit
def test_pytest_markers_configured(request):
    raw_markers = request.config.getini("markers")
    marker_names = {m.split(":")[0].strip() for m in raw_markers}
    expected = {"unit", "integration", "e2e", "slow"}
    assert expected.issubset(marker_names)
