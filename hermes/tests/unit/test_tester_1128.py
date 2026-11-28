"""The tester's tenth report (28.11), the coach's side.

2. «Разминка приостановлена на задаче 2 из 5 — напиши «дальше»…» closed the review of a game played after the
   warm-up: the break is said when the game starts (src/warmup.left_for_game), not by the next chat turn.
4. A session begun with a pasted FEN or link was called by that FEN or link (src/session_label.paste_label).
5. A Chess.com link the coach's server could not fetch came back to the student as English words: the import now
   answers with a code the site and the app say in the student's language (src/tools/game_url.GameUrlError.code).
"""

import json

import httpx
import pytest

from src import game_mode, warmup
from src.session_label import label, paste_label, position_words
from src.sessions import Board, Session
from src.tools import game_url

P1 = {"puzzle_id": "p1", "fen": "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1", "solution": ["d1d8"]}
P2 = {"puzzle_id": "p2", "fen": "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1", "solution": ["e1e8"]}
P3 = {"puzzle_id": "p3", "fen": "7k/6pp/8/8/8/8/6PP/R5K1 w - - 0 1", "solution": ["a1a8"]}


def _warm(at: int = 0):
    s = Session(id="s", user_id="u")
    puzzles = [P1, P2, P3]
    assert warmup.start(s, puzzles) == {"n": 1, "of": 3}
    for i in range(at + 1):
        if i:
            s.warmup["at"] = i
        s.set_board_state(puzzles[i]["fen"])
        warmup.put_up(s, puzzles[i]["puzzle_id"], puzzles[i]["fen"])
    return s


# ── 2. the warm-up's break said when the game starts ───────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_a_game_started_by_the_button_carries_the_break_and_the_review_after_it_has_none():
    s = _warm(at=1)
    s.add_message("user", "дальше")
    _, view = game_mode.start_game(s, "white", 1200, "quiet", in_turn=False)
    assert view["warmup_paused"] == {"n": 2, "of": 3}
    assert not s.warmup.get("tail")  # the screen says it; no answer of the server to end
    # the game is played and reviewed: «Разобрать» is the next chat turn
    s.add_message("user", "Разбери партию")
    assert warmup.paused(s) is None
    assert warmup.tail_line(s, "Разбор партии: …", "ru") == ""


@pytest.mark.unit
def test_a_game_started_from_the_chat_ends_that_answer_with_the_break_for_after_the_game():
    s = _warm(at=1)
    s.add_message("user", "давай сыграем")
    _, view = game_mode.start_game(s, "white", 1200, "quiet")
    assert view["warmup_paused"] == {"n": 2, "of": 3}
    assert warmup.tail_line(s, "Начинаем! Твой ход.", "ru") == (
        "Разминка приостановлена на задаче 2 из 3 — после партии напиши «дальше», чтобы вернуться к ней.")
    assert warmup.tail_line(s, "…", "ru") == ""  # once


@pytest.mark.unit
def test_дальше_after_the_game_brings_back_the_puzzle_it_stopped_at():
    s = _warm(at=1)
    game_mode.start_game(s, "white", 1200, "quiet", in_turn=False)
    for words in ("Разбери партию", "дальше"):
        s.add_message("user", words)
    assert warmup.resume(s) == P2


@pytest.mark.unit
def test_no_warm_up_or_a_break_already_said_adds_nothing_to_the_game():
    plain = Session(id="s", user_id="u")
    _, view = game_mode.start_game(plain, "white", 1200, "quiet", in_turn=False)
    assert "warmup_paused" not in view
    s = _warm()
    s.warmup["paused_said"] = True
    _, view = game_mode.start_game(s, "white", 1200, "quiet", in_turn=False)
    assert "warmup_paused" not in view
    over = _warm()
    over.warmup["over"] = True
    _, view = game_mode.start_game(over, "white", 1200, "quiet")
    assert "warmup_paused" not in view


@pytest.mark.unit
@pytest.mark.parametrize("lang, line", [
    ("en", "The warm-up is paused at puzzle 1 of 3 — after the game, say “next” to go back to it."),
    ("kk", "Жаттығу 3 есептің 1-есебінде тоқтатылды — партиядан кейін оған оралу үшін «келесі» деп жаз."),
])
def test_the_games_break_in_the_students_language(lang, line):
    s = _warm()
    s.add_message("user", "play")
    game_mode.start_game(s, "white", 1200, "quiet")
    assert warmup.tail_line(s, "", lang) == line


# ── 4. a pasted position or link named in words ────────────────────────────────────────────────────────────────────

TESTER_FEN = "1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1"


@pytest.mark.unit
@pytest.mark.parametrize("fen, lang, words", [
    (TESTER_FEN, "ru", "Позиция: король, ладья и пешка — король и ладья"),
    (TESTER_FEN, "en", "Position: king, rook and pawn vs king and rook"),
    (TESTER_FEN, "kk", "Позиция: патша, тура және сарбаз — патша және тура"),
    ("6k1/5ppp/8/8/8/8/2PP1PPP/6K1 w - - 0 1", "ru", "Позиция: король и 5 пешек — король и 3 пешки"),
    ("6k1/5ppp/8/8/8/8/1PPP1PPP/6K1 w - - 0 1", "ru", "Позиция, ход белых"),  # 9 pieces: past NAMED_PIECES
    ("4k3/8/8/8/8/8/8/RR2K3 w - - 0 1", "ru", "Позиция: король и 2 ладьи — король"),
    ("4k3/8/8/8/8/8/8/RR2K3 w - - 0 1", "en", "Position: king and 2 rooks vs king"),
    ("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1", "ru", "Позиция, ход чёрных"),
    ("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", "ru", "Начальная позиция"),
])
def test_a_position_is_named_by_what_stands_on_the_board(fen, lang, words):
    assert position_words(fen, lang) == words


@pytest.mark.unit
def test_a_session_of_a_pasted_fen_is_named_in_words_in_the_coachs_language():
    s = Session(id="s", user_id="u")
    s.add_message("user", TESTER_FEN)
    s.add_message("assistant", "Поставил позицию на доску. У белых лишняя пешка на b7.")
    assert label(s) == "Позиция: король, ладья и пешка — король и ладья"
    e = Session(id="e", user_id="u")
    e.add_message("user", TESTER_FEN)
    e.add_message("assistant", "The position is on the board. White has an extra pawn.")
    assert label(e) == "Position: king, rook and pawn vs king and rook"


@pytest.mark.unit
def test_a_link_is_named_by_the_game_it_brought_else_by_its_site():
    url = "https://www.chess.com/game/live/97872578329"
    s = Session(id="s", user_id="u")
    s.add_message("user", url)
    assert label(s) == "Партия с Chess.com"
    s.boards.append(Board(session_id="s", kind="study", pgn='[White "Hikaru"]\n[Black "Gravity_Chess"]\n\n1. e4 c5 1-0'))
    assert label(s) == "Hikaru – Gravity_Chess"
    assert paste_label("https://lichess.org/kAdOQKeh", None, "en") == "Game from Lichess"


@pytest.mark.unit
def test_a_pasted_record_is_named_by_its_players_else_by_its_opening():
    assert paste_label('[White "Иванов"]\n[Black "Петров"]\n[Result "0-1"]\n\n1. e4 e5 2. Nf3 Nc6 0-1') == "Иванов – Петров"
    assert paste_label("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 1-0") == \
        "1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 … 1-0"


@pytest.mark.unit
def test_words_said_still_name_the_session():
    s = Session(id="s", user_id="u")
    s.add_message("user", TESTER_FEN)
    s.add_message("user", "Может ли пешка превратиться в короля?")
    assert label(s) == "Может ли пешка превратиться в короля?"


# ── 5. a link the coach could not fetch, said by its code ──────────────────────────────────────────────────────────

def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.unit
@pytest.mark.parametrize("status, code", [
    (403, "unreachable:Chess.com"),   # Cloudflare refusing the server's address
    (503, "unreachable:Chess.com"),
    (404, "not_found:Chess.com"),
    (429, "rate_limited:Chess.com"),
])
def test_a_chesscom_answer_that_is_not_the_game_has_its_code(status, code):
    client = _client(lambda request: httpx.Response(status, text="<html>Just a moment…</html>"))
    with pytest.raises(game_url.GameUrlError) as caught:
        game_url.fetch_game_by_url("https://www.chess.com/game/live/97872578329", client)
    assert caught.value.code == code


@pytest.mark.unit
def test_a_challenge_page_with_200_is_not_the_game_either():
    client = _client(lambda request: httpx.Response(200, text="<html>Just a moment…</html>",
                                                     headers={"content-type": "text/html"}))
    with pytest.raises(game_url.GameUrlError) as caught:
        game_url.fetch_game_by_url("https://www.chess.com/game/live/97872578329", client)
    assert caught.value.code == "unreachable:Chess.com"


@pytest.mark.unit
def test_a_site_that_does_not_answer_is_unreachable_by_name():
    def refuse(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(game_url.GameUrlError) as caught:
        game_url.fetch_game_by_url("https://lichess.org/kAdOQKeh", _client(refuse))
    assert caught.value.code == "unreachable:Lichess"


@pytest.mark.unit
@pytest.mark.parametrize("url, code", [
    ("https://example.com/game/1", "not_game"),
    ("https://www.chess.com/member/hikaru", "not_game"),
    ("https://lichess.org/@/DrNykterstein", "not_game"),
])
def test_a_link_that_is_no_game(url, code):
    with pytest.raises(game_url.GameUrlError) as caught:
        game_url.parse_game_url(url)
    assert caught.value.code == code


@pytest.mark.unit
def test_the_tool_tells_the_model_how_the_student_brings_the_game_anyway(monkeypatch):
    def refused(url, client=None):
        raise game_url.GameUrlError("Chess.com did not give the game (HTTP 403).", "unreachable:Chess.com")

    monkeypatch.setattr(game_url, "fetch_game_by_url", refused)
    out = json.loads(game_url._handle_import_game_from_url({"url": "https://www.chess.com/game/live/1"}))
    assert out["code"] == "unreachable:Chess.com"
    assert "PGN" in out["student_hint"]


@pytest.mark.unit
def test_the_endpoint_answers_the_code_502_for_a_site_that_did_not_give_the_game(monkeypatch):
    from fastapi.testclient import TestClient

    from src import server

    def refused(url, client=None):
        raise game_url.GameUrlError("Chess.com did not give the game (HTTP 403).", "unreachable:Chess.com")

    def unknown(url, client=None):
        raise game_url.GameUrlError("Chess.com does not know this game.", "not_found:Chess.com")

    monkeypatch.setattr(game_url, "fetch_game_by_url", refused)
    monkeypatch.setattr(server, "_get_user_id", lambda request: "u")
    client = TestClient(server.app)
    r = client.post("/api/coach/import-url", json={"url": "https://www.chess.com/game/live/1"})
    assert (r.status_code, r.json()["detail"]) == (502, "unreachable:Chess.com")
    monkeypatch.setattr(game_url, "fetch_game_by_url", unknown)
    r = client.post("/api/coach/import-url", json={"url": "https://www.chess.com/game/live/1"})
    assert (r.status_code, r.json()["detail"]) == (400, "not_found:Chess.com")
