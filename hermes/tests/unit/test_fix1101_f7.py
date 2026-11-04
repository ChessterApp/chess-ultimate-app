"""Fix 01.11, package F7 (surfaces and openings) — the review-miss findings on 57bb4868.

  * The move comment (POST …/game/{id}/comment): every P1/P2 detector was inert there — config.detector_mode capped
    every detector at shadow on the "game" surface, and the endpoint gave the check no game record. Now only the
    relation detectors are capped, and the comment's check gets the game's moves when they lead to its board.
  * Opening names: a variation said bare («это Дракон», «Перед нами Найдорф», «Чёрные выбрали Дракон», "this is the
    Najdorf") was never read (Dragon 0/7); the told game record («Nf3 — и чёрные ответили d6: …») was read on an earlier
    position of the game when the context holds every position (the comment's); another branch of the board's own
    opening named by a name the identity check does not know («это сицилианская, вариант Свешникова» on 2...d6) was
    left to that check, which never saw it.

Precision: the board in the variation, a hedge, a plan, a person (not the line), a structure the book names at
another move order (the Stonewall) — none is cut.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import chess
import chess.pgn
import pytest

from src import config
from src.answer_check import CheckContext, check_sentence

B50 = "e4 c5 Nf3 d6"
NAJDORF = "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6"
DRAGON = "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6"
SVESHNIKOV = "e4 c5 Nf3 Nc6 d4 cxd4 Nxd4 Nf6 Nc3 e5 Ndb5 d6 Bg5 a6 Na3 b5"
LASKER_PELIKAN = "e4 c5 Nf3 Nc6 d4 cxd4 Nxd4 Nf6 Nc3 e5"
KAN = "e4 c5 Nf3 e6 d4 cxd4 Nxd4 a6"
TAIMANOV = "e4 c5 Nf3 e6 d4 cxd4 Nxd4 Nc6"
STONEWALL_EARLY = "d4 f5 c4 Nf6 g3 e6 Bg2 d5"
RUY_MORPHY = "e4 e5 Nf3 Nc6 Bb5 a6"
ITALIAN = "e4 e5 Nf3 Nc6 Bc4 Bc5"
EVANS = "e4 e5 Nf3 Nc6 Bc4 Bc5 b4"


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    from src.openings_book import warm_position_index

    warm_position_index()
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW", raising=False)
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")


def _game_ctx(moves: str, student=chess.WHITE, comment: bool = False) -> CheckContext:
    """A game on the board as the chat builds the check (*comment* False) or as the move comment does: the board and
    the game's PGN — every position of the game among the boards — on the "game" surface."""
    b = chess.Board()
    for san in moves.split():
        b.push_san(san)
    pgn = chess.pgn.Game.from_board(b).accept(chess.pgn.StringExporter(headers=False, variations=False, comments=False))
    ctx = CheckContext.from_fens([b.fen()], [pgn] if comment else [], student_color=student)
    ctx.game_moves = moves.split()
    first = 0 if student == chess.BLACK else 1
    ctx.game_engine_moves = [m for i, m in enumerate(moves.split()) if i % 2 == first]
    ctx.language = "ru"
    if comment:
        ctx.relation_surface = "game"
    return ctx


def _cut(moves: str, sentence: str, **kw) -> list:
    return check_sentence(sentence, _game_ctx(moves, **kw))


# ── the move-comment surface ─────────────────────────────────────────────────────────────────────────────────────
def test_a_move_comment_caps_only_the_relation_detectors():
    game = CheckContext.from_fens()
    game.relation_surface = "game"
    for name in config.DETECTOR_DEFAULTS:
        plain = config.detector_mode(name)
        capped = config.RELATION_DETECTORS - config.GAME_RECORD_RELATIONS  # cover_cause reads the record (miss2 01.11)
        expected = min(plain, "shadow", key=config._MODE_RANK.get) if name in capped else plain
        assert config.detector_mode(name, game) == expected, name
    lesson = CheckContext.from_fens()
    lesson.relation_surface = "lesson"
    assert all(config.detector_mode(n, lesson) == "off" for n in config.DETECTOR_DEFAULTS)


@pytest.mark.parametrize("moves,student,sentence", [
    ("e4 c5", chess.WHITE, "Чёрные отдали центральную пешку."),                       # gave_up: nothing taken yet
    ("e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5 Nxf7 Kxf7", chess.WHITE, "Чёрные отдали коня."),
    (B50, chess.WHITE, "Nf3 — и чёрные ответили d6: это вариант Найдорфа."),             # told record, open name
    (B50, chess.WHITE, "Получился Дракон."),
])
def test_a_false_game_sentence_is_cut_in_a_move_comment(moves, student, sentence):
    assert check_sentence(sentence, _game_ctx(moves, student, comment=True))


@pytest.mark.parametrize("moves,student,sentence", [
    ("e4 c5", chess.WHITE, "Чёрные ответили сицилианской защитой."),
    ("e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5 Nxf7 Kxf7", chess.WHITE, "Ты отдал коня за пешку, зато король чёрных вышел в центр."),
    (NAJDORF, chess.WHITE, "Nc3 — и чёрные ответили a6: это вариант Найдорфа."),
    (DRAGON, chess.WHITE, "Получился Дракон: слон пойдёт на g7."),
    (B50, chess.WHITE, "Отсюда возможен и Дракон, и Найдорф."),
])
def test_a_true_game_sentence_stays_in_a_move_comment(moves, student, sentence):
    assert check_sentence(sentence, _game_ctx(moves, student, comment=True)) == []


def test_the_relation_detectors_stay_shadow_in_a_move_comment(monkeypatch):
    ctx = _game_ctx("e4 e5 Nf3 Nc6 Bb5 a6", comment=True)
    # a relation claim is recorded at most: the relation detectors are not reviewed on comments yet
    assert all(config.detector_mode(n, ctx) != "on" for n in config.RELATION_DETECTORS - config.GAME_RECORD_RELATIONS)
    # a relation detector judged by the game's record follows the game-record rule (review-miss2 01.11)
    assert config.detector_mode("cover_cause", ctx) == config.detector_mode("cover_cause")


def test_the_record_must_lead_to_the_board():
    from src.server import _record_leads_to

    b = chess.Board()
    for san in "e4 e5 Nf3".split():
        b.push_san(san)
    assert _record_leads_to(["e4", "e5", "Nf3"], b.fen())
    assert not _record_leads_to(["e4", "e5"], b.fen())          # a view of an earlier position
    assert not _record_leads_to(["e4", "e5", "Nf3", "Zz9"], b.fen())
    assert not _record_leads_to(["e4"], None)


# the endpoint itself, as tests/unit/test_game_comment_check.py drives it
def _fake_completion(text: str):
    from src.quick_reply import QuickReply

    def fake(*, model, api_key, messages, on_delta=None, **kw):
        for i in range(0, len(text), 9):
            on_delta(text[i:i + 9])
        return QuickReply(text=text, model=model, prompt_tokens=30, completion_tokens=20)
    return fake


@pytest.fixture
def game_session(monkeypatch):
    from src import game_mode
    from src.game_mode import play_move, start_game
    from src.sessions import session_store

    session_store._sessions.clear()
    monkeypatch.setattr(game_mode, "_engine_move", lambda fen, elo: chess.Board(fen).parse_san("c5").uci()
                        if "c5" in [chess.Board(fen).san(m) for m in chess.Board(fen).legal_moves]
                        else next(iter(chess.Board(fen).legal_moves)).uci())
    monkeypatch.setattr(game_mode, "_evaluate", lambda fen, pov: (0, None))
    monkeypatch.setattr(config, "COACH_ANSWER_CHECK", True)
    session = session_store.create(user_id="f7-user")
    board, _ = start_game(session, "white", 1500)
    play_move(session, board, "e4")  # 1.e4 c5
    return session, board


def _comment(session, board, text):
    from fastapi.testclient import TestClient

    from src.server import app

    with patch("src.quick_reply.stream_completion", _fake_completion(text)), patch("src.server.log_event"):
        resp = TestClient(app).post(f"/api/coach/sessions/{session.id}/game/{board.id}/comment",
                                    headers={"X-User-Id": "f7-user"}, json={"locale": "ru"})
    assert resp.status_code == 200
    frames = [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: ")]
    return "".join(f.get("delta", "") for f in frames)


def test_the_comment_endpoint_cuts_a_false_record_sentence(game_session):
    session, board = game_session
    assert board.game_state["moves"] == ["e4", "c5"]
    shown = _comment(session, board, "Чёрные отдали центральную пешку. Это сицилианская защита.")
    assert "отдали" not in shown and "Это сицилианская защита." in shown


def test_the_comment_endpoint_keeps_a_true_comment(game_session):
    session, board = game_session
    text = "Чёрные ответили c5 — это сицилианская защита."
    assert _comment(session, board, text).strip() == text


# ── opening names said bare ──────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "Это Дракон.", "Перед нами Дракон.", "Получился Дракон.", "Чёрные выбрали Дракон.", "Ты играешь против Дракона.",
    "У нас вариант Дракона.", "Это Найдорф.", "Это Najdorf.", "Это Dragon.", "Перед тобой Свешников.",
    "У чёрных Дракон.", "2...d6 — это Найдорф.", "Чёрные сыграли d6 — это Дракон.",
    "Nf3 — и чёрные ответили d6: это сицилианский Дракон без g6.",
    "Nf3 — и чёрные ответили d6: это сицилианская, вариант Свешникова.",
    "Позиция после 1.e4 c5 2.Nf3 d6 — классический вариант сицилианской.",
    "Nf3 — и чёрные ответили d6: получилась Классическая система сицилианской.",
    "Чёрные выбрали Тайманов.",
])
def test_a_variation_the_board_is_not_is_cut(sentence):
    assert _cut(B50, sentence)


@pytest.mark.parametrize("moves,sentence", [
    (KAN, "Это Дракон."), (TAIMANOV, "Это Найдорф."), (ITALIAN, "Это Эванс."), (ITALIAN, "Перед нами гамбит Эванса."),
    (NAJDORF, "Это Дракон."), (DRAGON, "Это Найдорф."),
])
def test_another_variation_said_bare_is_cut(moves, sentence):
    assert _cut(moves, sentence)


@pytest.mark.parametrize("moves,sentence", [
    # the board is in it
    (NAJDORF, "Это Найдорф."), (NAJDORF, "Чёрные выбрали Найдорф."), (NAJDORF, "Ты играешь против Найдорфа."),
    (NAJDORF, "Это Najdorf."), (NAJDORF, "Позиция после 5...a6 — вариант Найдорфа."),
    (DRAGON, "Получился сицилианский Дракон."), (DRAGON, "Перед нами Дракон: слон пойдёт на g7."),
    (SVESHNIKOV, "Это Свешников."), (SVESHNIKOV, "Это челябинский вариант."),
    (LASKER_PELIKAN, "Это Свешников."),            # the book's Sveshnikov begins later inside the line on the board
    (TAIMANOV, "Получился Тайманов."), (EVANS, "Это Эванс."), (KAN, "Это Кан."),
    (KAN, "Это система Паульсена."),                # a name the book spreads: players' usage
    # hedges, plans, the line in general
    (B50, "Отсюда возможен и Дракон, и Найдорф."), (B50, "Дальше может получиться Найдорф."),
    (B50, "Это ещё не Найдорф: нужен ход a6."), (B50, "Если чёрные сыграют g6, будет Дракон."),
    (B50, "Здесь чёрные выбирают между Драконом и Найдорфом."), (B50, "Как в Драконе, слон может пойти на g7."),
    (B50, "Самый популярный ответ здесь — Найдорф."), (B50, "Это путь к Найдорфу или Дракону."),
    (B50, "Ты играешь сицилианскую, и Дракон — один из вариантов."), (B50, "Найдорф начинается после 5...a6."),
    # a person, not the line
    (NAJDORF, "Это Найдорф придумал ход a6."), (B50, "Найдорф придумал ход a6."),
    (RUY_MORPHY, "Это Морфи: развитие прежде всего."), (ITALIAN, "Это Морфи."),
    # a structure the book names at another move order
    (STONEWALL_EARLY, "Получился Стоунволл."), (STONEWALL_EARLY, "Это Стоунволл."),
])
def test_a_true_name_is_not_cut(moves, sentence):
    assert _cut(moves, sentence) == []


def test_a_bare_name_needs_the_end_of_its_clause():
    from src.answer_check_openings import _bare_heads

    low = "это найдорф придумал ход a6."
    assert _bare_heads(low, []) == []
    assert [w for _, _, w in _bare_heads("перед нами найдорф.", [])] == ["Najdorf"]
    assert [w for _, _, w in _bare_heads("это морфи.", [])] == []          # a great player said bare is a person
    start, _, _ = _bare_heads("это сицилианский дракон без g6.", [])[0]
    assert start == len("это ")                                             # the family word goes with the head


def test_the_told_record_is_read_on_the_board_not_on_an_earlier_position():
    """The comment's context holds every position of the game; «Nf3» of the told record was read on the board after
    2.Nf3 — where the Najdorf is still ahead — and the name passed as that move's line."""
    chat, comment = _game_ctx(B50), _game_ctx(B50, comment=True)
    s = "Nf3 — и чёрные ответили d6: это вариант Найдорфа."
    assert check_sentence(s, chat) and check_sentence(s, comment)
    assert check_sentence("Ход 2.c3 — вариант Алапина.", _game_ctx("e4 c5 c3 d6")) == []


def test_the_record_after_posle_is_no_condition():
    assert _cut(B50, "Позиция после 1.e4 c5 2.Nf3 d6 — Дракон.")
    assert _cut(B50, "Если после 2...d6 последует g6, будет Дракон.") == []


def test_open_plain_off_restores_the_old_reading(monkeypatch):
    monkeypatch.setenv("COACH_DETECTORS_OFF", "open_plain")
    assert _cut(B50, "Получился Дракон.") == []
    assert _cut(B50, "Перед нами Дракон.") == []
