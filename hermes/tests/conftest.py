# Test-scoped fixtures (currently inherits from root conftest.py)

import pytest


@pytest.fixture(autouse=True)
def _engine_steps_off(monkeypatch):
    """The engine's look at the student's idea and the check of the coach's
    recommendation run Stockfish (present on a developer's machine) and can
    start a real rewrite call: off unless a test switches them on."""
    from src import config

    monkeypatch.setattr(config, "COACH_HYPOTHETICAL_NOTE", False)
    monkeypatch.setattr(config, "COACH_MOVE_VERIFY", False)
