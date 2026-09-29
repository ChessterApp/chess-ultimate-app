"""Second speed pass (2026-09-28): game reviews, stalled streams, TWIC budgets, brief answers."""

import io
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import chess
import pytest

from src import config, server
from src.tools import stockfish
from src.tools._sqlite_budget import TIMEOUT_ERROR, install_timeout, is_timeout


# ── TWIC query budget ─────────────────────────────────────────────────────

def _slow_db() -> sqlite3.Connection:
    """A games table big enough that a LIKE scan outlives a zero budget."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE games (id INTEGER PRIMARY KEY, white_name TEXT, black_name TEXT, result TEXT,"
        " date TEXT, eco TEXT, opening TEXT, event TEXT, white_elo INTEGER, black_elo INTEGER)"
    )
    conn.execute(
        "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 200000) "
        "INSERT INTO games (white_name, black_name, eco, opening) "
        "SELECT 'Player' || i, 'Other' || i, 'C' || (i % 100), 'Opening' || i FROM n"
    )
    return conn


@pytest.mark.unit
def test_a_statement_past_the_budget_is_aborted():
    conn = _slow_db()
    install_timeout(conn, 0.0)
    with pytest.raises(sqlite3.OperationalError) as err:
        conn.execute("SELECT COUNT(*) FROM games WHERE white_name LIKE '%nobody%'").fetchone()
    assert is_timeout(err.value)


@pytest.mark.unit
def test_search_master_games_answers_a_timeout_with_an_error_the_model_can_skip():
    from src.tools import twic_search

    conn = _slow_db()
    with patch.object(twic_search, "install_timeout", lambda c: install_timeout(c, 0.0)), \
            patch.object(twic_search.sqlite3, "connect", return_value=conn):
        out = json.loads(twic_search._handle_search_master_games({"player": "Nobody"}))
    assert out == {"error": TIMEOUT_ERROR, "games": []}


@pytest.mark.unit
def test_player_openings_and_position_stats_time_out_softly():
    from src.tools import player_openings, position_stats

    with patch.object(player_openings, "install_timeout", lambda c: install_timeout(c, 0.0)):
        out = player_openings.get_player_openings("Nobody", conn=_slow_db())
    assert out["error"] == TIMEOUT_ERROR and out["openings"] == []

    conn = _slow_db()
    conn.execute(
        "CREATE TABLE move_stats (board_hash TEXT, move_san TEXT, games INTEGER,"
        " white_wins INTEGER, draws INTEGER, black_wins INTEGER)"
    )
    conn.execute(
        "INSERT INTO move_stats SELECT 'h' || id, 'e4', 1, 1, 0, 0 FROM games"
    )
    with patch.object(position_stats, "install_timeout", lambda c: install_timeout(c, 0.0)):
        out = position_stats.get_position_stats(chess.STARTING_FEN, conn=conn)
    assert out["error"] == TIMEOUT_ERROR


# ── Stockfish time cap ────────────────────────────────────────────────────

def _proc(output: str):
    proc = MagicMock()
    proc.stdin = MagicMock()
    proc.stdout = io.StringIO(output)
    proc.stderr = io.StringIO("")
    proc.wait = MagicMock(return_value=0)
    return proc


@pytest.mark.unit
def test_a_depth_search_is_also_bounded_by_time():
    proc = _proc("info depth 16 multipv 1 score cp 20 pv e2e4\nbestmove e2e4\n")
    with patch("subprocess.Popen", return_value=proc), patch.object(stockfish, "MAX_MS", 3000):
        result = stockfish.analyze_position(chess.STARTING_FEN, depth=16, multipv=1)
    written = "".join(c.args[0] for c in proc.stdin.write.call_args_list)
    assert "go depth 16 movetime 3000" in written
    assert "time_capped" not in result


@pytest.mark.unit
def test_a_run_stopped_by_the_cap_is_flagged_and_served_from_the_cache():
    stockfish.clear_analysis_cache()
    shallow = "info depth 11 multipv 1 score cp 20 pv e2e4\nbestmove e2e4\n"
    with patch("subprocess.Popen", side_effect=lambda *a, **k: _proc(shallow)) as popen, \
            patch.object(stockfish, "MAX_MS", 3000):
        first = stockfish.analyze_cached(chess.STARTING_FEN, depth=16, multipv=1)
        again = stockfish.analyze_cached(chess.STARTING_FEN, depth=16, multipv=1)
    assert first["time_capped"] is True
    assert again["best_move"] == "e2e4"
    assert popen.call_count == 1


# ── find_critical_moments carries the engine's answer ─────────────────────

def _scan_proc(evals_white: list, pvs: list):
    """Fake engine for find_critical_moments: one scored line with a pv per position."""
    lines = []
    for i, (value, pv) in enumerate(zip(evals_white, pvs)):
        cp = value if i % 2 == 0 else -value
        lines.append(f"info depth 12 seldepth 20 multipv 1 score cp {cp} pv {pv}\n")
        lines.append("bestmove x\n")
    proc = MagicMock()
    proc.stdin = MagicMock()
    proc.stdout = io.StringIO("".join(lines))
    return proc


@pytest.mark.unit
def test_each_moment_has_the_position_and_the_engine_line():
    from src.tools.critical_moments import find_critical_moments

    pgn = "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0"
    # Black's 3...Nf6 walks into mate; the engine wanted 3...g6 there. The final
    # position is mate, scored without the engine: seven engine calls.
    evals = [30, 30, 0, 0, 0, 0, 3000]
    pvs = ["e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g7g6 h5f3 g8f6", "h5f7"]
    result = find_critical_moments(pgn, _proc=_scan_proc(evals, pvs))
    moment = next(m for m in result["critical_moments"] if m["move"] == "Nf6")
    assert moment["fen_before"] == chess.Board(
        "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3").fen()
    assert moment["best_move"] == "g6"
    assert moment["best_line"] == "g6 Qf3 Nf6"
    assert result["engine_depth"] == 12


@pytest.mark.unit
def test_only_the_biggest_swings_are_kept_in_game_order():
    from src.tools import critical_moments

    pgn = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 1-0"
    # Every move swings: losses of 2, 5, 3, 4, 6, 2.5 pawns for the mover.
    evals = [0, -200, 300, 0, 400, -200, 50]
    pvs = ["e2e4"] * 7
    with patch.object(critical_moments, "MAX_MOMENTS", 3):
        result = critical_moments.find_critical_moments(pgn, threshold=1.5, _proc=_scan_proc(evals, pvs))
    assert [m["move"] for m in result["critical_moments"]] == ["e5", "Nc6", "Bc4"]
    assert result["moments_found"] == 6


# ── Gemini 3 thinking level ──────────────────────────────────────────────

@pytest.mark.unit
def test_gemini_3_gets_minimal_thinking_never_off(monkeypatch):
    monkeypatch.setattr(config, "COACH_GEMINI_REASONING_EFFORT", "none")
    assert server._gemini_reasoning("google/gemini-3.8-flash") == {"effort": "minimal"}
    monkeypatch.setattr(config, "COACH_GEMINI_REASONING_EFFORT", "low")
    assert server._gemini_reasoning("google/gemini-3.8-flash") == {"effort": "low"}
    monkeypatch.setattr(config, "COACH_GEMINI_REASONING_EFFORT", "")
    assert server._gemini_reasoning("google/gemini-3.8-flash") is None
    # Gemini 2 and every other family keep the framework's own handling.
    monkeypatch.setattr(config, "COACH_GEMINI_REASONING_EFFORT", "minimal")
    assert server._gemini_reasoning("google/gemini-2.5-flash") is None
    assert server._gemini_reasoning("deepseek/deepseek-v4.1-flash") is None


@pytest.mark.unit
def test_the_thinking_level_follows_the_model_after_a_failover(monkeypatch):
    monkeypatch.setattr(config, "COACH_GEMINI_REASONING_EFFORT", "minimal")
    agent = SimpleNamespace(model="deepseek/deepseek-v4.1-flash")
    agent._build_api_kwargs = lambda msgs: {
        "messages": msgs, "extra_body": {"provider": {"sort": "throughput"}, "reasoning": {"enabled": False}}}
    server._arm_gemini_reasoning(agent)

    assert agent._build_api_kwargs([])["extra_body"]["reasoning"] == {"enabled": False}
    agent.model = "google/gemini-3.8-flash"
    extra = agent._build_api_kwargs([])["extra_body"]
    assert extra == {"provider": {"sort": "throughput"}, "reasoning": {"effort": "minimal"}}


# ── A stream that dies mid-answer ────────────────────────────────────────

@pytest.mark.unit
def test_a_partial_stream_stub_flags_the_agent():
    responses = iter([SimpleNamespace(id="gen-1"), SimpleNamespace(id="partial-stream-stub")])
    agent = SimpleNamespace(_interruptible_streaming_api_call=lambda *a, **k: next(responses))
    server._watch_stream_cuts(agent)
    agent._interruptible_streaming_api_call({})
    assert agent._coach_stream_cut is False
    agent._interruptible_streaming_api_call({})
    assert agent._coach_stream_cut is True


@pytest.mark.unit
def test_framework_notices_are_recognised():
    assert server._is_framework_notice("\n\n⚠ Connection dropped mid tool-call; reconnecting…\n\n")
    assert server._is_framework_notice("\n\n⚠ Stream stalled mid tool-call (board_control); the action…")
    assert not server._is_framework_notice("Играй e4.")


@pytest.mark.unit
def test_the_stall_timeouts_default_to_the_coach_setting():
    import os

    # src.config set them at import unless the environment already had them.
    assert float(os.environ["HERMES_STREAM_READ_TIMEOUT"]) > 0
    assert float(os.environ["HERMES_STREAM_STALE_TIMEOUT"]) > 0
    assert config.COACH_STREAM_STALL_S == 30.0 or "COACH_STREAM_STALL_S" in os.environ


# ── Brief answers ─────────────────────────────────────────────────────────

@pytest.mark.unit
def test_brief_style_adds_the_length_rule_and_changes_the_version(monkeypatch):
    from src import prompt_builder

    monkeypatch.setattr(config, "COACH_ANSWER_STYLE", "full")
    full, _ = prompt_builder.build_system_prompt("soul", return_parts=True)
    full_version = prompt_builder._compute_prompt_version("soul")
    monkeypatch.setattr(config, "COACH_ANSWER_STYLE", "brief")
    brief, _ = prompt_builder.build_system_prompt("soul", return_parts=True)
    assert prompt_builder.BRIEF_ANSWER_LAYER not in full
    assert prompt_builder.BRIEF_ANSWER_LAYER in brief
    assert prompt_builder._compute_prompt_version("soul") != full_version


# ── Reply language at the end of the turn (2026-09-29) ───────────────────

@pytest.mark.unit
def test_the_reply_language_follows_the_message_not_the_notation():
    from src.prompt_builder import reply_language, reply_language_note

    assert reply_language("Что мне изучать дальше?", "en") == "Russian"
    assert reply_language("Осы жерде қандай жүріс жасаған дұрыс?", "ru") == "Kazakh"
    assert reply_language("What should I play here?", "ru") == "English"
    assert reply_language("Is Nxe5 good here?", "ru") == "English"
    # Moves alone carry no language: the interface decides.
    assert reply_language("Nf3?", "ru") == "Russian"
    assert reply_language("Nf3?", "en") == "English"
    assert reply_language("ok", "kz") == "Kazakh"
    assert "in Russian" in reply_language_note("Что играть?", "ru")


@pytest.mark.unit
def test_the_language_line_closes_the_turn_sent_to_the_model(monkeypatch):
    from fastapi.testclient import TestClient

    from src.user_profile import UserProfile

    captured = {}
    agent = MagicMock()
    agent.tools = []
    agent._api_call_count = 1
    agent.max_iterations = 5
    agent.session_prompt_tokens = agent.session_completion_tokens = 0

    def _chat(message, stream_callback=None):
        captured["message"] = message
        stream_callback("Играй e4.")
        return "Играй e4."

    agent.chat.side_effect = _chat
    with patch("src.server._create_agent", return_value=agent), \
            patch("src.server.load_user_profile", return_value=UserProfile(user_id="lang-user")), \
            patch("src.server.log_event"):
        resp = TestClient(server.app).post(
            "/api/coach/chat", headers={"X-User-Id": "lang-user"},
            json={"message": "Что мне изучать дальше?", "locale": "en"},
        )
    assert resp.status_code == 200
    assert captured["message"].rstrip().endswith("Never switch to another language.]")
    assert "write your whole answer in Russian" in captured["message"]
