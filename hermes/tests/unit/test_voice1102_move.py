"""Voice 02.11: a move proposed in words that cannot be played on the board now (detector ``word_move``).

Live 02.11 (production voice, a game, the student White to move 9 on r2qk1nr/ppp3pp/3p4/2b1p3/1nP5/3b1NP1/PP1P1PBP/
R1BQK2R): the coach proposed «пойти ферзём на d1» with the queen on d1, then «может попробуешь пойти пешкой на d2 на d3?»
and «Давай лучше пешкой на d3 пойдём» with Black's bishop on d3. Nothing cut them: the proposal reader took only a move
that is legal (for the engine to judge), so a move with no legal form was no proposal at all.

The class: a move told in words («пойти/сходить/сыграть ферзём (с d2) на d1», «пешкой на d3», «конём на f3», "move the
queen to d1", "push the d-pawn", a numbered move in words) after a proposal word (an imperative, «может», «давай»,
«попробуй», «предлагаю», «стоит», «лучше», …), for the side the proposal is for, with no legal move of that piece kind to
that square — the issue says why, from the board. Several pieces able to go there is fine. Left unjudged: a line
(«если», «после», «потом», a written move before it), the other side's move, the coach's own move in a game, a question
that is not a suggestion, a denial, a past board, a piece in the nominative (it may name where the piece stands).

The boards and the wordings are new (26 boards beyond the live one), text and voice (the squares said aloud, as the
voice check gets them through spoken_squares, and check_sentence(spoken=True)).
"""
from __future__ import annotations

import chess
import pytest

from src import config
from src.answer_check import CheckContext, check_sentence
from src.move_text import spoken_squares

MARK = "proposes a move that cannot be played"


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW", raising=False)
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")


def _b(moves: str, fen: str = chess.STARTING_FEN) -> str:
    board = chess.Board(fen)
    for m in moves.split():
        board.push_san(m)
    return board.fen()


LIVE = "r2qk1nr/ppp3pp/3p4/2b1p3/1nP5/3b1NP1/PP1P1PBP/R1BQK2R w KQkq - 0 9"
B = {
    "live": LIVE,
    "start": chess.STARTING_FEN,
    "italian_b": _b("e4 e5 Nf3 Nc6 Bc4"),
    "ruy_w": _b("e4 e5 Nf3 Nc6 Bb5 a6"),
    "sicil_b": _b("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3"),
    "french_b": _b("e4 e6 d4 d5 e5"),
    "qgd_w": _b("d4 d5 c4 e6 Nc3 Nf6"),
    "caro_b": _b("e4 c6 d4 d5 Nc3"),
    "kid_w": _b("d4 Nf6 c4 g6 Nc3 Bg7 e4 d6"),
    "scand_w": _b("e4 d5 exd5 Qxd5"),
    "london_b": _b("d4 d5 Bf4 Nf6 e3"),
    "legal_w": _b("e4 e5 Nf3 d6 Bc4 Bg4 Nc3 g6 Nxe5 Bxd1"),
    "check_w": _b("e4 e5 Nf3 Nc6 Bb5 Nf6 d3 Bb4+"),
    "kpk_w": "8/5pk1/6p1/8/3K4/8/5PP1/8 w - - 0 40",
    "rook_b": "8/8/4k3/8/2R5/4K3/r7/8 b - - 0 50",
    "promo_w": "8/P6k/8/8/8/8/6K1/8 w - - 0 60",
    "pinned_w": "4k3/8/8/b7/8/8/3N4/4K3 w - - 0 1",
    "incheck_b": "4k3/8/8/8/8/8/8/4R1K1 b - - 0 1",
    "ep_w": _b("e4 a6 e5 d5"),
    "rooks_w": "3k4/8/8/8/8/8/6K1/R6R w - - 0 1",
    "knights_w": "4k3/8/8/8/8/8/8/1N2K1N1 w - - 0 1",
    "bishop_w": "4k3/8/8/8/8/8/8/2B1K3 w - - 0 1",
    "queen_w": "4k3/8/8/8/8/8/8/3QK3 w - - 0 1",
    "e4_b": _b("e4"),
    "blocked_b": "4k3/3p4/3N4/8/8/8/8/4K3 b - - 0 1",
    "two_q_w": "4k3/8/8/8/8/8/8/Q2QK3 w - - 0 1",
    "nimzo_b": _b("d4 Nf6 c4 e6 Nc3"),
}


def _issues(sentence: str, board: str, *, voice: bool = False, student=None, question: str = "") -> list:
    ctx = CheckContext.from_fens([B.get(board, board)], [], question=question)
    if student is not None:
        ctx.student_color = student
    text = spoken_squares(sentence) if voice else sentence
    return [i for i in check_sentence(text, ctx, spoken=voice) if MARK in i]


# ── the live sentences ─────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("voice", [False, True])
@pytest.mark.parametrize("sentence, why", [
    ("Может, попробуешь пойти ферзём на d1?", "the white queen already stands on d1"),
    ("Давай пойдём ферзём на d1, чтобы прикрыть короля.", "the white queen already stands on d1"),
    ("Может попробуешь пойти пешкой на d2 на d3?", "d3 is occupied by the black bishop"),
    ("Давай лучше пешкой на d3 пойдём, чтобы прогнать этого слона.", "d3 is occupied by the black bishop"),
])
def test_live_sentences_are_cut(sentence, why, voice):
    got = _issues(sentence, "live", voice=voice, student=chess.WHITE)
    assert len(got) == 1 and why in got[0], got


def test_live_sentences_said_aloud():
    assert "already stands on d1" in _issues("Может, пойдёшь ферзём на дэ один?", "live", voice=True, student=chess.WHITE)[0]
    assert "occupied by the black bishop" in _issues("Давай пешкой на дэ три пойдём.", "live", voice=True,
                                                     student=chess.WHITE)[0]


# ── moves that cannot be played: cut, with the reason from the board ──────────────────────────────────────────────
FALSE = [
    ("start", "Сыграй ферзём на d4.", "blocked by the white pawn on d2"),
    ("start", "Поставь слона на c4, он там сильнее.", "blocked by the white pawn on e2"),
    ("start", "Попробуй конём на e4.", "no white knight can reach e4"),
    ("start", "Давай конём на d2.", "d2 is occupied by White's own pawn"),
    ("italian_b", "Давай пойдём конём на e5.", "e5 is occupied by Black's own pawn"),
    ("italian_b", "Можно пешкой на e4.", "e4 is occupied by the white pawn"),
    ("ruy_w", "Пойди пешкой на e5.", "e5 is occupied by the black pawn"),
    ("sicil_b", "Сыграй слоном на h6.", "blocked by the black pawn on g7"),
    ("french_b", "Предлагаю пойти пешкой на e5.", "e5 is occupied by the white pawn"),
    ("qgd_w", "Стоит сыграть слоном на b5.", "blocked by the white pawn on e2"),
    ("caro_b", "Лучше всего пешкой на d4.", "d4 is occupied by the white pawn"),
    ("kid_w", "Сходи конём на e4.", "e4 is occupied by White's own pawn"),
    ("scand_w", "Попробуй пешкой на d5.", "no white pawn can reach d5"),
    ("london_b", "Двинь слона на d6.", "blocked by the black pawn on e7"),
    ("legal_w", "Пойди ферзём на d1.", "White has no queen"),
    ("check_w", "Сыграй конём на g5.", "king is in check from the black bishop on b4"),
    ("kpk_w", "Сыграй слоном на e4.", "White has no bishop"),
    ("rook_b", "Сходи ладьёй на c4.", "no black rook can reach c4"),
    ("promo_w", "Иди королём на g8.", "no white king can reach g8"),
    ("pinned_w", "Сыграй конём на f3.", "is pinned to the white king by the black bishop on a5"),
    ("incheck_b", "Давай королём на e7.", "e7 is attacked by the white rook on e1"),
    ("ep_w", "Сыграй пешкой на f6.", "there is nothing to take on f6"),
    ("knights_w", "Поставь коня на e4.", "no white knight can reach e4"),
    ("bishop_w", "Поставь слона на c4.", "no white bishop can reach c4"),
    ("queen_w", "Возьми ферзём на d7.", "there is nothing to take on d7"),
    ("e4_b", "Давай пешкой на e4.", "no black pawn can reach e4"),
    ("blocked_b", "Пойди пешкой на d5.", "the pawn on d7 is blocked by the white knight on d6"),
    ("nimzo_b", "Сыграй ферзём на h4.", "blocked by the black knight on f6"),
    ("nimzo_b", "Возьми слоном на c3.", "no black bishop can reach c3"),
    ("two_q_w", "Бей ферзём на d8.", "there is nothing to take on d8"),
    ("live", "Можешь пойти ферзём с d1 на d2.", "d2 is occupied by White's own pawn"),
    ("live", "Сыграй пешкой с e2 на e4.", "there is no white pawn on e2"),
    ("live", "Можно сыграть конём на e5 или ферзём на d1.", "the white queen already stands on d1"),
    ("scand_w", "Уведи ферзя на a5.", "no white queen can reach a5"),  # the student addressed: the side to move
    # English
    ("live", "Move the queen to d1.", "the white queen already stands on d1"),
    ("live", "You could push the d-pawn.", "the d-pawn on d2 cannot move: d3 in front of it is occupied by the black bishop"),
    ("qgd_w", "Move the bishop to b5.", "blocked by the white pawn on e2"),
    ("kid_w", "I suggest you put the knight on e4.", "e4 is occupied by White's own pawn"),
    ("french_b", "Двинь d-пешку.", "the d-pawn on d5 cannot move: d4 in front of it is occupied by the white pawn"),
    # a numbered move in words, for the move now
    ("live", "Давай 9. ферзём на d1.", "the white queen already stands on d1"),
]


@pytest.mark.parametrize("voice", [False, True])
@pytest.mark.parametrize("board, sentence, why", FALSE)
def test_unplayable_proposal_is_cut(board, sentence, why, voice):
    got = _issues(sentence, board, voice=voice)
    assert got and why in got[0], got


# ── moves that can be played (one piece or several): not cut ──────────────────────────────────────────────────────
TRUE = [
    ("live", "Может, сыграешь конём на h4?"),
    ("live", "Давай слоном на f1 отойдём."),
    ("start", "Сыграй конём на f3."),
    ("start", "Пойди пешкой на e4."),
    ("italian_b", "Сыграй слоном на c5."),
    ("ruy_w", "Попробуй слоном на a6."),  # the capture Bxa6, told without «взять»
    ("ruy_w", "Сходи конём на e5."),
    ("sicil_b", "Давай пешкой на d5."),
    ("french_b", "Сыграй пешкой на c5."),
    ("qgd_w", "Поставь слона на g5."),
    ("caro_b", "Можно пешкой на e4."),
    ("kid_w", "Стоит сыграть конём на f3."),
    ("scand_w", "Давай конём на c3, с темпом."),
    ("london_b", "Сыграй пешкой на c5."),
    ("legal_w", "Сыграй слоном на f7."),
    ("check_w", "Поставь пешку на c3."),
    ("kpk_w", "Иди королём на e5."),
    ("rook_b", "Сыграй ладьёй на a3."),
    ("promo_w", "Двигай пешку на a8."),
    ("pinned_w", "Пойди королём на f2."),
    ("incheck_b", "Сходи королём на d7."),
    ("ep_w", "Возьми пешкой на d6."),
    ("ep_w", "Побей пешку d5 пешкой e5."),
    ("rooks_w", "Поставь ладью на d1."),  # both rooks can: fine
    ("knights_w", "Поставь коня на d2."),
    ("bishop_w", "Поставь слона на g5."),
    ("queen_w", "Поставь ферзя на d7."),
    ("e4_b", "Сыграй пешкой на e5."),
    ("blocked_b", "Сходи королём на e7."),
    ("two_q_w", "Сыграй ферзём на d4."),
    ("nimzo_b", "Сыграй слоном на b4."),
    ("qgd_w", "Push the e-pawn."),
    ("french_b", "Двинь c-пешку."),
    ("live", "Сыграй пешкой на h3, а потом подумаем."),
]


@pytest.mark.parametrize("voice", [False, True])
@pytest.mark.parametrize("board, sentence", TRUE)
def test_playable_proposal_is_not_cut(board, sentence, voice):
    assert _issues(sentence, board, voice=voice) == []


# ── scope: what is left unjudged ──────────────────────────────────────────────────────────────────────────────────
UNJUDGED = [
    ("live", "Если пойти ферзём на d1, слон уйдёт."),                 # a condition
    ("live", "После Bxc4 можно пойти ферзём на d1."),                 # a line written before it
    ("live", "Потом пойдёшь ферзём на d1."),                          # later
    ("live", "Сначала h3, потом ферзём на d1."),
    ("live", "Вместо того чтобы пойти ферзём на d1, сыграй h3."),
    ("live", "Тогда стоит пойти ферзём на d1."),                      # goes on with the line before
    ("live", "Соперник может пойти ферзём на d8."),                   # the other side
    ("live", "Чёрным стоит пойти ферзём на d1."),
    ("live", "Соперник опасен: может пойти ферзём на h4."),
    ("live", "Можно ли пойти ферзём на d1?"),                         # a question, not a suggestion
    ("live", "Хочешь пойти ферзём на d1?"),
    ("live", "Пойти ферзём на d1 нельзя — он уже там."),              # a denial
    ("live", "Не стоит идти ферзём на d1."),
    ("live", "Надо было пойти ферзём на d1."),                        # a past board
    ("live", "Лучше ферзь на d1 оставить."),                          # the piece told where it stands
    ("live", "Лучше ферзь на d1."),
    ("live", "Лучше защитить пешку на d3."),                          # another verb's object
    ("live", "Стоит обратить внимание на слона на d3."),
    ("live", "Давай 12. конём на h4."),                               # another move of the game
    ("live", "If you move the queen to d1, the bishop wins."),
    ("live", "Black will move the queen to d8."),
    ("start", "Лучше ладью на a1 пока не трогать."),
    ("nimzo_b", "Возьми коня на c3."),                                # the piece taken, not the mover
    ("nimzo_b", "Take the knight on c3."),
    ("nimzo_b", "Попробуй забрать пешку на d4."),
    # no side named and the other side could make it: «Можно увести ферзя на a5» with Black's queen on d5, White to move
    ("scand_w", "Можно увести ферзя на a5 или d6."),
    ("scand_w", "Лучше ферзём на e6."),
]


@pytest.mark.parametrize("voice", [False, True])
@pytest.mark.parametrize("board, sentence", UNJUDGED)
def test_out_of_scope_is_left_unjudged(board, sentence, voice):
    assert _issues(sentence, board, voice=voice) == []


def test_the_coachs_own_move_in_a_game_is_left_unjudged():
    assert _issues("Давай я пойду ферзём на d1.", "live", student=chess.WHITE) == []


def test_in_a_game_the_student_addressed_is_judged_for_the_student():
    # the student White to move: «уведи ферзя на a5» is his queen (d1), which cannot get there — Black's could
    got = _issues("Уведи ферзя на a5.", "scand_w", student=chess.WHITE)
    assert got and "no white queen can reach a5" in got[0]
    # …but «можно» names no one: Black's queen may be meant
    assert _issues("Можно увести ферзя на a5.", "scand_w", student=chess.WHITE) == []
    # a side named is judged for that side when it is to move
    got = _issues("Белым стоит пойти ферзём на a5.", "scand_w")
    assert got and "no white queen can reach a5" in got[0]


def test_in_a_game_the_engines_turn_is_left_unjudged():
    # the student plays Black and it is White's (the engine's) move: the proposal is for after a reply not yet made
    assert _issues("Попробуй пойти ферзём на d1.", "live", student=chess.BLACK) == []
    assert _issues("Попробуй пойти ферзём на d1.", "live", student=chess.WHITE)


def test_the_students_idea_board_is_another_board():
    # «А если я сыграю Qe2?» — the coach may talk about the board after it; a move legal there is not judged here
    ctx = CheckContext.from_fens([LIVE, _b("Qe2", LIVE)], [], question="А если я сыграю Qe2?")
    ctx.student_color = chess.WHITE
    assert [i for i in check_sentence("Попробуй пойти ферзём на d1.", ctx) if MARK in i] == []


def test_the_line_the_sentence_before_wrote():
    ctx = CheckContext.from_fens([LIVE], [], question="")
    ctx.student_color = chess.WHITE
    check_sentence("После Qe2 Bxe2 Kxe2 у белых нет ферзя.", ctx)
    # «Давай королём на f1» — legal at the line's end? The king is on e2 there; f1 is reachable: not judged now
    assert [i for i in check_sentence("Давай королём на f1.", ctx) if MARK in i] == []


def test_switch_off_and_shadow(monkeypatch):
    monkeypatch.setenv("COACH_DETECTORS_SHADOW", "word_move")
    ctx = CheckContext.from_fens([LIVE], [], question="")
    assert [i for i in check_sentence("Давай пойдём ферзём на d1.", ctx) if MARK in i] == []
    assert any(r[0] == "word_move" for r in ctx.detector_shadow)
    monkeypatch.setenv("COACH_DETECTORS_OFF", "word_move")
    assert _issues("Давай пойдём ферзём на d1.", "live") == []


def test_lesson_tutor_never_judged():
    ctx = CheckContext.from_fens([LIVE], [], question="")
    ctx.relation_surface = "lesson"
    assert [i for i in check_sentence("Давай пойдём ферзём на d1.", ctx) if MARK in i] == []


# ── the move reader: the forms it reads ───────────────────────────────────────────────────────────────────────────
def test_reader_forms():
    from src.move_words import file_pushes, prose_moves

    board = chess.Board(LIVE)
    one = prose_moves("пешкой на d2 на d3", board)[0]
    assert (one["from"], one["to"]) == (chess.D2, chess.D3)
    two = prose_moves("пойти ферзем d1", board)[0]
    assert two["to"] == chess.D1 and not two["nominative"]
    assert prose_moves("сыграть ферзь d4", chess.Board())[0]["nominative"]
    assert prose_moves("the queen on d1", board)[0]["nominative"]
    assert not prose_moves("put the queen on d1", board)[0]["nominative"]
    assert [p["file"] for p in file_pushes("push the d-pawn", board)] == [3]
    assert file_pushes("двинь пешку d2 на d3", board) == []  # a square, not a file


# ── through the voice check itself (POST /api/coach/voice/check), as the browser sends a sentence said ────────────
def test_the_voice_check_endpoint_cuts_the_live_sentences():
    from fastapi.testclient import TestClient

    from src.server import app

    client = TestClient(app)
    said = ["Может, попробуешь пойти ферзём на дэ один?", "Давай лучше пешкой на дэ три пойдём, чтобы прогнать слона."]
    for i, text in enumerate(said):
        resp = client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-move-1102"},
                           json={"text": text, "fen": LIVE, "question": "что мне делать?", "previous": " ".join(said[:i]),
                                 "engine": False})
        assert resp.status_code == 200
        issues = resp.json()["issues"]
        assert any(MARK in x for x in issues), issues
    resp = client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-move-1102"},
                       json={"text": "Может, сыграешь конём на аш четыре?", "fen": LIVE, "question": "что мне делать?",
                             "engine": False})
    assert resp.status_code == 200 and not any(MARK in x for x in resp.json()["issues"])
