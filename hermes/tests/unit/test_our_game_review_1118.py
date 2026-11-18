"""«Разобрать» after a game with the coach reviews THAT game, and its opening has the book's name (18.11).

Checked on production and on the stand, 18.11. The button under a finished game sends «Разбери нашу партию: где я
ошибся и что стоило играть.» with the page's study board — the page names the game's board only while the game is
on. The turn had no game on its board: the coach answered «Полную запись завершённой партии я не вижу… пришли её ходы
или PGN», or «Сейчас ход белых. Хорошее продолжение — 3.Кxe5», as in a game still going. And in a review the opening
was named from memory: the Blackburne Shilling trap came out «гамбит Блэкберна — Клостермана», then «— Стэйнтона».
"""

import time

import pytest

from src import game_mode
from src.opening_knowledge import game_opening_note
from src.server import AFTER_GAME_WINDOW_S, _our_game_board
from src.sessions import session_store

pytestmark = pytest.mark.unit

BUTTON = {
    "ru": "Разбери нашу партию: где я ошибся и что стоило играть.",
    "en": "Review our game: where did I go wrong and what should I have played?",
    "kk": "Партиямызды талда: мен қайда қателестім және не ойнау керек еді?",
}
SHILLING = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Nd4 4. Nxe5 Qg5 5. Nxf7 Qxg2 6. Rf1 Qxe4+ 7. Be2 Nf3# 0-1"


@pytest.fixture(autouse=True)
def _clean():
    session_store._sessions.clear()
    yield
    session_store._sessions.clear()


def _played(moves=("e4", "e5", "Nf3", "Nc6"), finished=True):
    """A session as the page leaves it: the study board first, then a game with the coach — resigned, or still on."""
    session = session_store.create(user_id="our-game")
    study = session.ensure_board()
    game, _ = game_mode.start_game(session, "white", 1200)
    game.game_state["moves"] = list(moves)
    session.save_board(game)
    if finished:
        game_mode.resign(session, game)
    session.set_active_board(study.id)          # what the page's request does: it names the study board
    return session, study, game


# ── which game the review is of ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("language", ["ru", "en", "kk"])
def test_the_buttons_words_with_the_study_board_are_about_the_game_just_played(language):
    """The three texts the site and the app send from «Разобрать»."""
    session, study, game = _played()
    assert _our_game_board(session, study, BUTTON[language]) is game


def test_any_review_request_right_after_the_game_is_about_it():
    """«Где я ошибся?» typed instead of the button: the game has just ended and the board holds no other game."""
    session, study, game = _played()
    assert _our_game_board(session, study, "Где я ошибся?") is game
    assert _our_game_board(session, study, "разбери партию") is game


def test_a_game_the_student_loaded_is_the_one_reviewed_unless_ours_is_named():
    """10.11: the review takes the game of the board the student looks at. «Нашу партию» names the coach's game."""
    session, study, game = _played()
    study.load_pgn(SHILLING)
    session.save_board(study)
    assert _our_game_board(session, study, "Разбери эту партию") is None
    assert _our_game_board(session, study, BUTTON["ru"]) is game


def test_a_game_long_over_is_reviewed_only_by_name():
    session, study, game = _played()
    game.game_state["finished_at"] = time.time() - AFTER_GAME_WINDOW_S - 60
    assert _our_game_board(session, study, "Где я ошибся?") is None
    assert _our_game_board(session, study, BUTTON["ru"]) is game


def test_a_game_in_progress_is_never_reviewed():
    """The coach hints there; and with a newer game on, the older finished one is not «our game» either."""
    session, study, game = _played(finished=False)
    assert _our_game_board(session, study, BUTTON["ru"]) is None
    session, study, old = _played()
    game_mode.start_game(session, "white", 1200)
    assert _our_game_board(session, study, BUTTON["ru"]) is None


def test_nothing_changes_for_other_words_and_other_boards():
    session, study, game = _played()
    assert _our_game_board(session, study, "Разбери эту позицию") is None      # a question about a position
    assert _our_game_board(session, study, "Какой здесь план?") is None
    assert _our_game_board(session, game, BUTTON["ru"]) is None                 # the page sent the game's own board
    empty = session_store.create(user_id="our-game-none")
    assert _our_game_board(empty, empty.ensure_board(), BUTTON["ru"]) is None   # no game was played
    unmoved, study2, _ = _played(moves=())
    assert _our_game_board(unmoved, study2, BUTTON["ru"]) is None                # resigned before a move: nothing to review


# ── the opening's name ──────────────────────────────────────────────────────────────────────────

def test_the_opening_of_the_game_is_told_by_the_book_with_its_russian_name():
    note = game_opening_note(SHILLING)
    assert "C50 Blackburne Shilling Trap — по-русски: ловушка Блэкберна (гамбит Блэкберна–Костича)" in note
    assert "name it only so" in note and "not from memory" in note


def test_a_line_without_a_russian_name_is_told_with_its_familys():
    """«Французская защита» is in the table; «Knight Variation» is not — it is not to be translated anew."""
    note = game_opening_note("1. e4 e6 2. Nf3 d5")
    assert "French Defense" in note and "по-русски: французская защита" in note and "Latin letters" in note


def test_a_game_the_book_does_not_know_gets_no_note():
    assert game_opening_note("") == "" and game_opening_note(None) == ""
    assert game_opening_note("not a game") == ""


def test_the_voice_review_tool_tells_the_opening_too(monkeypatch):
    """review_game — the voice page's call: its note carries the same block."""
    from src.tools import review_game as rg

    monkeypatch.setattr(rg, "find_critical_moments", lambda pgn: {"total_moves": 7, "engine_depth": 12, "critical_moments": []})
    out = rg.review_game(SHILLING)
    assert "ловушка Блэкберна (гамбит Блэкберна–Костича)" in out["note"]


# ── the turn ────────────────────────────────────────────────────────────────────────────────────

H = {"X-User-Id": "our-game-turn"}


@pytest.fixture
def turn(monkeypatch):
    """The text turn with the model and the scan replaced: (client, seen)."""
    from fastapi.testclient import TestClient

    from src import config, server
    from src.middleware.rate_limiter import rate_limiter
    from src.tools import critical_moments as cm

    rate_limiter.reset()
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-not-a-key")
    monkeypatch.setattr(config, "COACH_TWO_STAGE", False)
    monkeypatch.setattr(config, "COACH_TOOL_SUBSET", False, raising=False)
    monkeypatch.setattr(cm, "find_critical_moments", lambda pgn, *a, **k: {
        "total_moves": 7, "engine_depth": 12, "evals_from": "white", "critical_moments": []})
    monkeypatch.setattr(server, "_board_review_fits", lambda pgn: (True, {}))
    seen: dict = {}

    def fake_chat(agent, message, session_id, stream_callback=None, student_message="", game_step=False):
        seen["message"] = message
        if stream_callback:
            stream_callback("Сдаваться было рано.")
        return "Сдаваться было рано."

    monkeypatch.setattr(server, "_chat_in_session", fake_chat)
    yield TestClient(server.app), seen
    rate_limiter.reset()


def _say(client, sid, text, **kw):
    import json

    with client.stream("POST", "/api/coach/chat", json={"message": text, "session_id": sid, "locale": "ru", **kw},
                       headers=H) as r:
        return [json.loads(line[5:]) for line in r.iter_lines() if line.startswith("data:")]


def test_the_button_sent_with_the_study_board_makes_the_game_the_turns_board(turn):
    """What the page sends after a resignation: the study board's id and the game's final position. The turn is
    about the game — its board is the session's active one, and the game is not started over or played on."""
    client, seen = turn
    sid = client.post("/api/coach/sessions", json={}, headers=H).json()["id"]
    session = session_store.get(sid, user_id=H["X-User-Id"])
    study = session.ensure_board()
    game, _ = game_mode.start_game(session, "white", 1200)
    game.game_state["moves"] = ["e4", "e6", "Nf3", "d5"]
    session.save_board(game)
    game_mode.resign(session, game)
    _say(client, sid, BUTTON["ru"], board_id=study.id, fen="rnbqkbnr/ppp2ppp/4p3/3p4/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3")
    session = session_store.get(sid, user_id=H["X-User-Id"])
    assert session.active_board_id == game.id
    assert [b.kind for b in session.boards].count("game") == 1 and game.game_state["status"] == "finished"
    assert "French Defense" in seen["message"] and "французская защита" in seen["message"]


def test_a_review_of_a_game_on_the_board_is_told_its_opening_by_the_book(turn):
    """«Разбери эту партию» over a loaded game — and the pasted game the same way: the book's name is in the turn."""
    client, seen = turn
    sid = client.post("/api/coach/sessions", json={}, headers=H).json()["id"]
    client.post(f"/api/coach/sessions/{sid}/boards", json={"kind": "master_game", "pgn": SHILLING}, headers=H)
    _say(client, sid, "Разбери эту партию")
    assert "ловушка Блэкберна (гамбит Блэкберна–Костича)" in seen["message"]
    seen.clear()
    sid = client.post("/api/coach/sessions", json={}, headers=H).json()["id"]
    _say(client, sid, SHILLING)
    assert "ловушка Блэкберна (гамбит Блэкберна–Костича)" in seen.get("message", "")
