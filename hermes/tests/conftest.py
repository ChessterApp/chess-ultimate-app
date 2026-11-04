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


@pytest.fixture(autouse=True)
def _engine_pool_off(monkeypatch):
    """Persistent Stockfish processes (src/engine_pool.py) and the board-change precompute (src/engine_precompute.py,
    plan 31.10 P7) are on in production; the unit tests mock the per-search process and its output, and a
    background search must not race a test's own engine calls. The P7 tests switch them on themselves."""
    import os

    from src import config

    if os.environ.get("HERMES_TEST_STOCKFISH_POOL") != "1":  # =1: the suite on the pool (a parity run)
        monkeypatch.setattr(config, "STOCKFISH_POOL", False)
    monkeypatch.setattr(config, "COACH_PRECOMPUTE", False)


@pytest.fixture(autouse=True)
def _rewrite_proof_on(monkeypatch):
    """The rewrite proof (fix1102 K6) ships in shadow (config.COACH_REWRITE_PROOF, live run 04.11); the tests written
    for it judge it switched on. The shadow tests switch it back themselves."""
    from src import config

    monkeypatch.setattr(config, "COACH_REWRITE_PROOF", "on")
