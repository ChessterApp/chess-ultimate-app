"""The games-database checks ship in shadow (04.11, the last check before the update).

The last check of 04.11 (fresh sentences beside production ecdadca9) still found true sentences cut by both checks of
src/answer_check_db.py: the loaded game's moves 15 of 311 true sentences, the database claims 1. Each check now has
its own switch, off | shadow | on, default shadow: it runs, records what it would cut in ``ctx.db_shadow`` and the text
turn logs it as one ``db_check`` event; nothing is cut until the log is reviewed and the switch is turned on.
  COACH_DB_CLAIM_CHECK    — claims about the database with no empty search of the turn;
  COACH_LOADED_GAME_CHECK — a move of the loaded database game told wrong.
"""

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import chess
import chess.pgn
import pytest

from src import answer_check_db as acd
from src import config
from src.answer_check import CheckContext, check_sentence

KT = """[Event "Hoogovens"]
[Date "1999.01.20"]
[White "Kasparov, Garry"]
[Black "Topalov, Veselin"]
[Result "1-0"]

1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.Be3 Bg7 5.Qd2 c6 6.f3 b5 7.Nge2 Nbd7 8.Bh6 Bxh6 9.Qxh6 Bb7 10.a3 e5 11.O-O-O Qe7
12.Kb1 a6 13.Nc1 O-O-O 14.Nb3 exd4 15.Rxd4 c5 16.Rd1 Nb6 17.g3 Kb8 18.Na5 Ba8 19.Bh3 d5 20.Qf4+ Ka7 21.Rhe1 d4
22.Nd5 Nbxd5 23.exd5 Qd6 24.Rxd4 cxd4 25.Re7+ Kb6 26.Qxd4+ Kxa5 27.b4+ Ka4 28.Qc3 Qxd5 29.Ra7 Bb7 30.Rxb7 Qc4
31.Qxf6 Kxa3 32.Qxa6+ Kxb4 33.c3+ Kxc3 34.Qa1+ Kd2 35.Qb2+ Kd1 36.Bf1 Rd2 37.Rd7 Rxd7 38.Bxc4 bxc4 39.Qxh8 Rd3
40.Qa8 c3 41.Qa4+ Ke1 42.f4 f5 43.Kc1 Rd2 44.Qa7 1-0
"""
WRONG_MOVE = "Каспаров рокировал в короткую сторону на 11-м ходу."  # 11.O-O-O
NO_ACCESS = "У меня нет доступа к базе партий."  # no database tool ran


def _loaded():
    game = chess.pgn.read_game(io.StringIO(KT))
    board = game.board()
    for move in game.mainline_moves():
        board.push(move)
    ctx = CheckContext.from_fens([None, board.fen(), board.fen()], [KT], question="")
    ctx.db_tracked = True
    acd.note_board_game(ctx, KT)
    return ctx


def _plain():
    ctx = CheckContext.from_fens([chess.STARTING_FEN], question="")
    ctx.db_tracked = True
    return ctx


CASES = [("loaded_game", "COACH_LOADED_GAME_CHECK", _loaded, WRONG_MOVE),
         ("db_claim", "COACH_DB_CLAIM_CHECK", _plain, NO_ACCESS)]


@pytest.mark.unit
def test_both_checks_ship_in_shadow():
    """The values in src/config.py with no environment set — the subprocess reads the module fresh."""
    env = {k: v for k, v in os.environ.items() if k not in ("COACH_DB_CLAIM_CHECK", "COACH_LOADED_GAME_CHECK")}
    out = subprocess.run([sys.executable, "-c", "from src import config; "
                          "print(config.COACH_DB_CLAIM_CHECK, config.COACH_LOADED_GAME_CHECK)"],
                         cwd=Path(__file__).resolve().parents[2], env=env, capture_output=True, text=True, check=True)
    assert out.stdout.split() == ["shadow", "shadow"]


@pytest.mark.unit
def test_the_environment_turns_a_check_on():
    env = {**os.environ, "COACH_DB_CLAIM_CHECK": "on", "COACH_LOADED_GAME_CHECK": "off"}
    out = subprocess.run([sys.executable, "-c", "from src.answer_check_db import mode; "
                          "print(mode('db_claim'), mode('loaded_game'))"],
                         cwd=Path(__file__).resolve().parents[2], env=env, capture_output=True, text=True, check=True)
    assert out.stdout.split() == ["on", "off"]


@pytest.mark.unit
@pytest.mark.parametrize("part,switch,make,sentence", CASES)
def test_shadow_records_and_never_cuts(monkeypatch, part, switch, make, sentence):
    monkeypatch.setattr(config, switch, "shadow")
    ctx = make()
    assert check_sentence(sentence, ctx) == []
    [(got_part, said, issues)] = ctx.db_shadow
    assert got_part == part and issues and said.strip() == sentence
    record = acd.log_record(ctx)
    assert record["db_shadow_total"] == 1 and record["db_shadow"][0]["part"] == part
    assert record["modes"][part] == "shadow"


@pytest.mark.unit
@pytest.mark.parametrize("part,switch,make,sentence", CASES)
def test_on_cuts(monkeypatch, part, switch, make, sentence):
    monkeypatch.setattr(config, switch, "on")
    ctx = make()
    assert check_sentence(sentence, ctx)
    assert ctx.db_shadow == [] and acd.log_record(ctx) is None


@pytest.mark.unit
@pytest.mark.parametrize("part,switch,make,sentence", CASES)
def test_off_neither_cuts_nor_records(monkeypatch, part, switch, make, sentence):
    monkeypatch.setattr(config, switch, "off")
    with patch.object(acd, "db_claim_issues" if part == "db_claim" else "loaded_game_issues",
                      side_effect=AssertionError("ran while off")):
        ctx = make()
        assert check_sentence(sentence, ctx) == []
    assert ctx.db_shadow == []


@pytest.mark.unit
@pytest.mark.parametrize("value", ["", "maybe", "SHADOW"])
def test_a_value_nobody_meant_is_shadow(monkeypatch, value):
    monkeypatch.setattr(config, "COACH_DB_CLAIM_CHECK", value)
    assert acd.mode("db_claim") == ("off" if value == "" else "shadow")


@pytest.mark.unit
def test_each_switch_is_its_own(monkeypatch):
    monkeypatch.setattr(config, "COACH_DB_CLAIM_CHECK", "on")
    monkeypatch.setattr(config, "COACH_LOADED_GAME_CHECK", "shadow")
    ctx = _loaded()
    assert check_sentence(WRONG_MOVE, ctx) == [] and ctx.db_shadow
    assert check_sentence(NO_ACCESS, _plain())


@pytest.mark.unit
def test_the_log_record_stays_within_one_row():
    ctx = _plain()
    ctx.db_shadow.extend(("db_claim", "x" * 400, ["y" * 400]) for _ in range(40))
    record = acd.log_record(ctx)
    assert record["db_shadow_total"] == 40
    assert len(json.dumps(record["db_shadow"], ensure_ascii=False).encode()) <= acd.SHADOW_BYTES


# ── the text turn: shown and logged in shadow, cut when on ─────────────────────────────────────────────────────────

FIX = "Расскажу партию по памяти."


@pytest.mark.unit
class TestTurn:
    @pytest.fixture(autouse=True)
    def _turn(self, monkeypatch):
        from fastapi.testclient import TestClient

        from src.middleware.rate_limiter import rate_limiter
        from src.sessions import session_store

        session_store._sessions.clear()
        rate_limiter.reset()
        for name, value in (("COACH_TWO_STAGE", False), ("COACH_ENGINE_NOTE", False), ("COACH_OPENING_PRESTEP", False),
                            ("COACH_SITE_PUZZLE_LOOKUP", False), ("COACH_ANSWER_CHECK", True),
                            ("COACH_ANSWER_FIX", True), ("COACH_RELATION_CHECK", "off")):
            monkeypatch.setattr(config, name, value)
        self.monkeypatch = monkeypatch
        self.client = TestClient(__import__("src.server", fromlist=["app"]).app)
        yield
        session_store._sessions.clear()
        rate_limiter.reset()

    def _turn_with(self, text):
        from unittest.mock import MagicMock

        from src.quick_reply import QuickReply
        from src.user_profile import UserProfile

        agent = MagicMock()
        agent.tools = []
        agent.model = "deepseek/deepseek-v4.1-flash"
        agent._api_call_count = 1
        agent.max_iterations = 5
        agent.session_prompt_tokens = agent.session_completion_tokens = agent.session_cache_read_tokens = 0

        def _chat(message, stream_callback=None):
            stream_callback(text)
            return text

        agent.chat.side_effect = _chat

        def _fix(**kw):
            kw["on_delta"](FIX)
            return QuickReply(model=kw["model"])

        events = []
        with patch("src.server._create_agent", return_value=agent), \
                patch("src.server.load_user_profile", return_value=UserProfile(user_id="db-switch")), \
                patch("src.quick_reply.stream_completion", side_effect=_fix), \
                patch("src.server.engine_note", return_value=None), \
                patch("src.server.log_event", side_effect=lambda name, **kw: events.append((name, kw))):
            resp = self.client.post("/api/coach/chat", headers={"X-User-Id": "db-switch"},
                                    json={"message": "Покажи партию Фишера", "fen": chess.STARTING_FEN})
        assert resp.status_code == 200
        frames = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
        return "".join(f.get("delta", "") for f in frames), events

    def test_shadow_shows_the_sentence_and_logs_what_it_would_cut(self):
        self.monkeypatch.setattr(config, "COACH_DB_CLAIM_CHECK", "shadow")
        text, events = self._turn_with(NO_ACCESS)
        assert text == NO_ACCESS
        [record] = [kw["payload"] for name, kw in events if name == "db_check"]
        assert record["db_shadow"][0]["part"] == "db_claim" and record["db_shadow"][0]["sentence"] == NO_ACCESS
        assert record["modes"] == {"db_claim": "shadow", "loaded_game": config.COACH_LOADED_GAME_CHECK}

    def test_on_cuts_the_sentence(self):
        self.monkeypatch.setattr(config, "COACH_DB_CLAIM_CHECK", "on")
        text, events = self._turn_with(NO_ACCESS)
        assert NO_ACCESS not in text and FIX in text
        assert not [name for name, _ in events if name == "db_check"]
