"""Voice 02.11, the reviews of voice-1102 (review-fp, review-miss): the false cuts of word_move and castle_reason
closed by class, and the miss classes a mechanism closes.

False cuts (true sentences, each class on several boards, both colours, written and said aloud):
  * a move left for later by what follows it («Поставь ладью на e1 после рокировки», «…, когда рокируешься», «…, как
    только уйдут конь и ферзь») or by a time word before it («Позже …», «Через пару ходов …»);
  * a manoeuvre: a route («перевести коня на g3 через d2 и f1»), a verb of regrouping («переведи коня на d3») — only
    «already there», «own piece there», «no such piece» and the pin are judged for it;
  * a step told before the move («Рокируйся и ставь ладью на e1»): the move is judged after the step;
  * the opponent's castling («Соперник не может рокироваться: его король под шахом», «Чёрные под шахом — …»);
  * a reason bound to another predicate («…, и уйти королём на d2 тоже нельзя: поле d2 бьёт слон b4»);
  * a piece's square read as a castling square («…, хотя ладья d1 стоит на линии d»).
Misses closed: castling proposed when illegal (castle_advice), «я бы сходил», the proposal wordings no frame read, a
written move after a proposal word (word_move_san), a bare «Конём на e4!» and «Конём на d3 сыграй», the reason in the
sentence before or after «а», «не пройдёт», «в длинную сторону», «а это поле под ударом», a piece named as the reason,
squares said after «поле», «с», «через», «бьёт».
"""
from __future__ import annotations

import re

import chess
import pytest

from src import config
from src.answer_check import CheckContext, check_sentence
from src.move_text import spoken_squares


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


_L = {"a": "а", "b": "бэ", "c": "цэ", "d": "дэ", "e": "е", "f": "эф", "g": "жэ", "h": "аш"}
_N = {"1": "один", "2": "два", "3": "три", "4": "четыре", "5": "пять", "6": "шесть", "7": "семь", "8": "восемь"}


def _said(text: str) -> str:
    return re.sub(r"(?<![A-Za-z0-9])([a-h])([1-8])(?![0-9A-Za-z])", lambda m: f"{_L[m.group(1)]} {_N[m.group(2)]}", text)


def _issues(text: str, fen: str, student=None, voice: bool = False, before: str = "", game: bool = False) -> list:
    ctx = CheckContext.from_fens([fen], question="что мне делать?", student_color=student)
    if game:
        ctx.game_moves = ["(game)"]
    for s in [x for x in re.split(r"(?<=[.!?])\s+", before) if x]:
        check_sentence(spoken_squares(_said(s)) if voice else s, ctx, spoken=voice)
    return check_sentence(spoken_squares(_said(text)) if voice else text, ctx, spoken=voice)


LIVE = "r2qk1nr/ppp3pp/3p4/2b1p3/1nP5/3b1NP1/PP1P1PBP/R1BQK2R w KQkq - 0 9"
ITALIAN = "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
SCOTCH = "r1b1k2r/ppppnppp/2n2q2/2b5/3NP3/2P1B3/PP3PPP/RN1QKB1R w KQkq - 1 7"
CHIGORIN = "r1b2rk1/2q1bppp/p2p1n2/npp1p3/3PP3/2P2N1P/PPB2PP1/RNBQR1K1 w - - 1 12"
EVANS_B = "r1bqk1nr/pppp1ppp/2n5/b7/2BpP3/2P2N2/P4PPP/RNBQ1RK1 b kq - 1 7"
KID = "r1bq1rk1/ppp1npbp/3p1np1/3Pp3/2P1P3/2N2N2/PP2BPPP/R1BQ1RK1 w - - 1 9"
G8ATT = "r1bqk2r/ppp1n1pp/2np1p2/2b1p3/2B1P3/2NPBN2/PPP2PPP/R2QK2R w KQkq - 0 7"
CARO = "r2qkb1r/pp1n1pp1/2p1pn1p/7P/3P4/3Q1NN1/PPPB1PP1/R3K2R w KQkq - 2 12"
DRAGON = "r1bq1rk1/pp2ppbp/2np1np1/8/3NP3/2N1BP2/PPPQ2PP/R3KB1R w KQ - 3 9"
LEGAL_TRAP = "rn1qkbnr/ppp2B1p/3p2p1/4N3/4P3/2N5/PPPP1PPP/R1BbK2R b KQkq - 0 6"
NIMZO_CHK = "rnbqk2r/pppp1ppp/4pn2/8/1bPP4/5N2/PP2PPPP/RNBQKB1R w KQkq - 2 4"
FRIED = "r1bq1b1r/ppp3pp/2n1k3/3np3/2B5/5Q2/PPPP1PPP/RNB1K2R w KQ - 2 8"
LONG_B = "r3k2r/ppp1qppp/2npbn2/4p3/4P3/2N1BN2/PPP1QPPP/3RKB1R b Kkq - 0 9"
SCAND = _b("e4 d5 exd5 Qxd5")
W, BL = chess.WHITE, chess.BLACK

# ── false cuts: true sentences that must pass ─────────────────────────────────────────────────────────────────────
TRUE = [
    # a move left for later
    (ITALIAN, W, "Поставь ладью на e1 после рокировки."),
    (ITALIAN, W, "Ставь ладью на e1, когда рокируешься."),
    (SCOTCH, W, "Позже можно поставить ладью на d1, когда рокируешься и уведёшь ферзя."),
    (CHIGORIN, W, "Поставь ладью на d1, как только уйдут конь, слон и ферзь."),
    (EVANS_B, BL, "Поставь ладью на e8 после рокировки."),
    (ITALIAN, W, "Поставь ладью на e1, но сначала рокируйся."),
    (KID, W, "Через пару ходов можно поставить коня на d3."),
    # a manoeuvre
    (CHIGORIN, W, "Давай переведём коня на g3 через d2 и f1."),
    (CHIGORIN, W, "Стоит перевести коня на g3 через d2 и f1 — это классический манёвр."),
    (KID, W, "Можно перевести коня на d3 через e1."),
    (KID, W, "Стоит перевести коня на b3 через d2."),
    (KID, W, "Переведи коня на d3."),
    # a step told before the move
    (ITALIAN, W, "Рокируйся и ставь ладью на e1."),
    (G8ATT, W, "Рокируйся и поставь ладью на e1."),
    (CARO, W, "Рокируйся длинно и ставь ладью h1 на e1."),
    (DRAGON, W, "Рокируйся длинно и ставь короля на b1."),
    # the opponent's castling
    (LEGAL_TRAP, W, "Теперь чёрные под шахом и рокироваться не могут."),
    (LEGAL_TRAP, W, "Соперник не может рокироваться: его король под шахом."),
    (LEGAL_TRAP, W, "Противнику сейчас нельзя рокироваться, ведь король под шахом от слона f7."),
    (NIMZO_CHK, BL, "Соперник не может рокироваться: его король под шахом."),
    # a reason bound to another predicate; a piece's square
    (NIMZO_CHK, W, "Рокироваться нельзя — ты под шахом, и уйти королём на d2 тоже нельзя: поле d2 бьёт слон b4."),
    (LONG_B, None, "Длинная рокировка возможна, хотя ладья d1 стоит на линии d: её закрывает твоя пешка d6."),
    # true castling advice and reasons
    (ITALIAN, W, "Рокируйся коротко."),
    (ITALIAN, W, "Давай рокируемся, а потом поставим ладью на e1."),
    (ITALIAN, W, "Сыграй O-O."),
    (LIVE, W, "Давай рокируемся, когда уведёшь слона d3."),
    (LIVE, W, "Не рокируйся пока, сначала прогони слона d3."),
    (LIVE, W, "Рокироваться нельзя из-за слона d3."),
    (LIVE, W, "Короткой рокировке мешает слон на d3."),
    (LIVE, W, "Слон на d3 держит под прицелом поле f1, поэтому рокироваться коротко нельзя."),
    (LIVE, W, "Сыграй конём на h4."),
    # «можно увести ферзя на a5» names no one: Black's queen may be meant
    (SCAND, W, "Можно увести ферзя на a5."),
]


@pytest.mark.parametrize("voice", [False, True], ids=["written", "said"])
@pytest.mark.parametrize("fen, student, text", TRUE)
def test_true_sentences_are_not_cut(fen, student, text, voice):
    got = _issues(text, fen, student=student, voice=voice, game=student is not None)
    assert got == [], got


def test_opponent_moved_king_is_not_the_students():
    assert _issues("Соперник не может рокироваться: его король уже ходил.", FRIED, student=W, game=True) == []


# ── misses closed ────────────────────────────────────────────────────────────────────────────────────────────────
FALSE = [
    # castling proposed when it cannot be played (live board: f1 attacked by the bishop d3)
    (LIVE, W, "Рокируйся коротко.", "castling is proposed"),
    (LIVE, W, "Сделай короткую рокировку.", "castling is proposed"),
    (LIVE, W, "Давай рокируемся.", "castling is proposed"),
    (LIVE, W, "Пора рокироваться.", "castling is proposed"),
    (LIVE, W, "Я бы рокировался коротко.", "castling is proposed"),
    (LIVE, W, "Можешь рокироваться коротко.", "castling is proposed"),
    (LIVE, W, "Короткая рокировка доступна.", "castling is proposed"),
    (LIVE, W, "Сыграй O-O.", "proposes castling (O-O)"),
    (LIVE, W, "Сыграй королём на g1.", "proposes castling (O-O)"),
    (DRAGON, W, "Рокируйся коротко.", "castling is proposed"),
    (NIMZO_CHK, W, "Давай сделаем короткую рокировку.", "castling is proposed"),
    # a move told in words
    (LIVE, None, "Я бы сходил ферзём на d1.", "already stands on d1"),
    (LIVE, W, "Сыграй ферзём d1.", "already stands on d1"),
    (LIVE, W, "Ферзём на d1!", "already stands on d1"),
    (LIVE, W, "Ферзём на d1 сыграй.", "already stands on d1"),
    (ITALIAN, None, "Отправь ладью на e1.", "e1 is occupied"),
    (ITALIAN, None, "Давай уведём ферзя на d1.", "already stands on d1"),
    (ITALIAN, None, "Тебе нужен ход конём на f3.", "already stands on f3"),
    (ITALIAN, None, "Здесь хорош ход слоном на c4.", "already stands on c4"),
    (ITALIAN, None, "How about bringing the knight to f3?", "already stands on f3"),
    (ITALIAN, None, "Давай возьмём конём на d4.", "nothing to take on d4"),
    (ITALIAN, None, "Может, конём на f3?", "already stands on f3"),
    (ITALIAN, None, "Переставь ладью на e1.", "e1 is occupied"),
    # a written move after a proposal word
    (ITALIAN, None, "Сыграй Qh6.", "cannot be played"),
    (ITALIAN, None, "Сыграй Nd5.", "no white knight can reach d5"),
    # castling reasons
    (LIVE, W, "Рокироваться нельзя из-за слона c5.", "attacks none of"),
    (LIVE, W, "Короткой рокировке мешает слон на c5.", "attacks none of"),
    (LIVE, W, "Короткая рокировка не пройдёт: поле f2 под боем слона.", "f2 is not on the king's path"),
    (LIVE, W, "Слон на c5 бьёт поле f2, а по правилам проходить через битое поле при рокировке нельзя.",
     "f2 is not on the king's path"),
    (LIVE, W, "Рокировке в короткую сторону мешает слон c5, который бьёт поле f2.", "castling reason is wrong"),
    (LIVE, W, "Нельзя рокироваться коротко, потому что слон c5 держит под прицелом поле f2.", "f2 is not on the king's path"),
    (ITALIAN, W, "Рокироваться коротко нельзя: король встанет на g1, а это поле под ударом.", "nothing of Black's attacks g1"),
]


@pytest.mark.parametrize("voice", [False, True], ids=["written", "said"])
@pytest.mark.parametrize("fen, student, text, mark", FALSE)
def test_false_sentences_are_cut(fen, student, text, mark, voice):
    if voice and not re.search(r"[а-яё]", text):
        pytest.skip("English is not said in the Russian voice")
    got = _issues(text, fen, student=student, voice=voice, game=student is not None)
    assert any(mark in x for x in got), got


def test_reason_in_the_sentence_before():
    got = _issues("Поэтому рокироваться коротко нельзя.", LIVE, student=W, before="Поле f2 под боем слона c5.")
    assert any("f2 is not on the king's path" in x for x in got), got
    got = _issues("Поэтому рокироваться коротко нельзя.", LIVE, student=W, voice=True, before="Поле f2 под боем слона c5.")
    assert any("f2 is not on the king's path" in x for x in got), got
    # the true reason told before passes
    assert _issues("Поэтому рокироваться коротко нельзя.", LIVE, student=W, before="Поле f1 под боем слона d3.") == []


def test_castling_advice_on_the_opponents_turn_or_for_later_is_not_judged():
    # the student plays Black: White (the engine) to move — the advice is for after its reply
    assert _issues("Рокируйся коротко.", LIVE, student=BL, game=True) == []
    assert _issues("Рокируйся коротко при первой возможности.", LIVE, student=W) == []
    assert _issues("Скоро можно будет рокироваться.", LIVE, student=W) == []


def test_advice_with_can_in_a_game_and_on_a_move_question():
    # «Можно сыграть …» in a game on the student's turn is the student's move, though the opponent's knight b4 could
    # go to c2 (review-miss 02.11 #6)
    got = _issues("Можно сыграть конём на c2.", LIVE, student=W, game=True)
    assert any("c2" in x for x in got), got
    # …outside a game, or with the opponent named in the sentence before, either side's move: not judged
    assert _issues("Можно сыграть конём на c2.", LIVE) == []
    assert _issues("Можно сыграть конём на c2.", LIVE, student=W, game=True,
                   before="Соперник сейчас думает над ответом.") == []
    # «Можешь рокироваться коротко» outside a game answers «что мне делать?» for this board
    got = _issues("Можешь спокойно рокироваться коротко.", LIVE)
    assert any("castling is proposed" in x for x in got), got
    # …the legal castling passes
    assert _issues("Можешь спокойно рокироваться коротко.", ITALIAN) == []
    ctx = CheckContext.from_fens([LIVE], question="расскажи про правила рокировки")
    assert not any("castling is proposed" in x for x in check_sentence("Можешь рокироваться коротко.", ctx))


def test_spoken_squares_after_square_words():
    assert spoken_squares("поле же один под боем слона") == "поле g1 под боем слона"
    assert spoken_squares("сходи ладьёй с е один на дэ два, это хороший вариант") == "сходи ладьёй с e1 на d2, это хороший вариант"
    assert spoken_squares("король пройдёт через эф один, а оно под боем") == "король пройдёт через f1, а оно под боем"
    assert spoken_squares("Слон бьёт же две пешки и это очень неприятно для белых.") == \
        "Слон бьёт же две пешки и это очень неприятно для белых."


def test_new_detectors_have_switches(monkeypatch):
    text = "Рокируйся коротко."
    monkeypatch.setenv("COACH_DETECTORS_OFF", "castle_advice")
    assert _issues(text, LIVE, student=W) == []
    monkeypatch.setenv("COACH_DETECTORS_OFF", "word_move_san")
    assert _issues("Сыграй Qh6.", ITALIAN) == []
