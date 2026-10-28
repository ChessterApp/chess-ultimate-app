"""A tool whose coach session could not be loaded does not run as if there were no game (28.10).

The tool-level lookups (sessions._tool_session, game_play._session, stockfish._live_game_turn,
identity.resolve_user_id) caught every exception and returned None, SessionLoadError included:
a tool reached on a cold cache while Supabase failed ran in "no game" mode — e.g. the engine's
best line handed out in a live game, or «No coach session to start the game in».
"""

import json

import pytest
from tools.registry import registry

from src import identity, sessions
from src.session_persistence import SessionLoadError
from src.sessions import session_store
from src.tools import discover_and_register, game_play, stockfish

SID = "cold-session-1028"


@pytest.fixture(autouse=True)
def _tools():
    discover_and_register()


@pytest.fixture
def load_fails(monkeypatch):
    def get(session_id, user_id=None):
        raise SessionLoadError(session_id, "the boards")

    monkeypatch.setattr(session_store, "get", get)


@pytest.fixture
def lookup_breaks(monkeypatch):
    def get(session_id, user_id=None):
        raise RuntimeError("some other bug")

    monkeypatch.setattr(session_store, "get", get)


@pytest.mark.unit
def test_the_tool_session_helpers_do_not_turn_a_failed_load_into_no_session(load_fails):
    kwargs = {"session_id": SID}
    for lookup in (sessions._tool_session, sessions.session_for, sessions.board_lock_for,
                   game_play._session):
        with pytest.raises(SessionLoadError):
            lookup(kwargs)
    with pytest.raises(SessionLoadError):
        stockfish._live_game_turn("8/8/8/8/8/8/8/K6k w - - 0 1", kwargs)
    with pytest.raises(SessionLoadError):
        identity.resolve_user_id({}, kwargs)


@pytest.mark.unit
def test_other_lookup_errors_are_still_handled_as_before(lookup_breaks):
    kwargs = {"session_id": SID}
    assert sessions._tool_session(kwargs) is None
    assert game_play._session(kwargs) is None
    assert stockfish._live_game_turn("8/8/8/8/8/8/8/K6k w - - 0 1", kwargs) is None
    token = identity.current_user_id.set("ctx-user")
    try:
        assert identity.resolve_user_id({}, kwargs) == "ctx-user"
    finally:
        identity.current_user_id.reset(token)


@pytest.mark.unit
@pytest.mark.parametrize("name,args", [
    ("start_game", {"color": "white"}),
    ("analyze_position", {"fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"}),
    ("get_puzzle", {}),
])
def test_a_tool_on_an_unloaded_session_answers_a_clear_error_not_a_no_game_result(load_fails, monkeypatch, name, args):
    engine = {"best_move": "e7e5", "lines": [{"pv": "e7e5 g1f3", "score": 0.3, "depth": 16}]}
    monkeypatch.setattr(stockfish, "analyze_cached", lambda **_: engine)
    out = json.loads(registry.dispatch(name, args, session_id=SID))
    assert "session" in str(out.get("error", "")).lower() and "could not be loaded" in out["error"]
    assert out.get("hint")  # the model is told not to answer as if there were no game
    assert "lines" not in out and "puzzles" not in out and not out.get("ok")
