"""Fix 02.11, package K7 — the small false-flag groups of verify1102 (VERDICT §6.5) and the lost mat07.

  * A book name is not language: «… — это линия «French Defense: Advance Variation, Extended Bishop Swap»» was cut as an
    English sentence (live theory move-french-adv) and left a headless rest. A quoted title with no Cyrillic in it and
    a run of capitalised Latin words are names; English prose is still told.
  * «… e7... точнее, стоит как есть)» (live ep-expired, st2#3): «точнее», «вернее», «то есть» after an ellipsis refine
    the same sentence — only a retraction («нет», «стоп», «хм», "wait") is thinking aloud.
  * The evaluator is not the holder of a verdict: «движок даёт белым решающий перевес» (+9.8) was read as Black's
    verdict, «движок даёт им …» resolved «им» to the engine, and «a3 … проигрывают: движок даёт чёрным …» judged the
    engine's verdict on a named move against the board before it (fresh-fp d13#3, e09#1, b13#3).
  * «английское начало, вариант четырёх коней» is the English's Four Knights Variation (A28), not the Four Knights Game
    (fresh-fp a20#0): a name said as a variation is matched to the board line's variations.
  * «Ты выиграл пешку на d4» over 3...cxd4 4.Nxd4 (fresh-miss mat07): to WIN a unit is to come out of the exchange ahead.

The boards and the wordings below are new (not the reported ones), each with a negative twin that must still be cut.
"""
from __future__ import annotations

import chess
import pytest

from src import config
from src.answer_check import META_ISSUE, CheckContext, SentenceGate, check_sentence, language_issue


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    from src.openings_book import warm_position_index

    warm_position_index()
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW", raising=False)
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")


def _game_ctx(moves: str, student=chess.WHITE) -> CheckContext:
    sans = moves.split()
    b = chess.Board()
    for m in sans:
        b.push_san(m)
    ctx = CheckContext.from_fens([b.fen()], [], question="")
    first = 0 if student == chess.BLACK else 1
    ctx.game_engine_moves = [m for i, m in enumerate(sans) if i % 2 == first]
    ctx.game_moves = list(sans)
    ctx.student_color = student
    return ctx


def _eval_ctx(fen: str, ev: float) -> CheckContext:
    ctx = CheckContext.from_fens([fen])
    ctx.engine_eval = ev
    return ctx


def _evals(issues: list) -> list:
    return [i for i in issues if i.startswith("the engine evaluates")]


# ── names are not language ──────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "Это вариант «Sicilian Defense: Najdorf Variation, English Attack», самый популярный в последние годы.",
    "После 5...a6 получается Sicilian Defense: Najdorf Variation, Opocensky Variation.",
    "Сейчас на доске Ruy Lopez: Morphy Defense, Closed — главная линия испанской.",
    "Партию называют «The Evergreen Game».",
])
def test_a_book_name_in_a_russian_sentence_is_not_english(sentence):
    assert language_issue(sentence, "ru") is None


@pytest.mark.parametrize("sentence", [
    "This is the main line of the Najdorf and White usually plays the English Attack here.",
    "I'll show you the Sicilian Defense on the board now.",
    "Black wants to play d5 later, so keep the centre closed for now and develop.",
])
def test_english_prose_in_a_russian_answer_is_still_told(sentence):
    assert language_issue(sentence, "ru") == "this sentence is in English; the whole answer must be in Russian"


# ── a refinement after an ellipsis is the same sentence ───────────────────────────────────────────────────────────────
NIMZO = "rnbqk2r/pppp1ppp/4pn2/8/1bPP4/2N5/PP2PPPP/R1BQKBNR w KQkq - 2 4"


@pytest.mark.parametrize("text", [
    "Слон b4 связывает коня c3... точнее, связывает его с королём e1. ",
    "Ферзь может пойти на c2... вернее, на b3, чтобы бить по слону. ",
    "Белые хотят сыграть a3... то есть прогнать слона. ",
])
def test_a_refinement_after_an_ellipsis_is_not_planning(text):
    gate = SentenceGate(CheckContext.from_fens([NIMZO]))
    out = gate.feed(text) + gate.flush()
    assert not any(META_ISSUE in o[1] for o in out)


@pytest.mark.parametrize("text", [
    "Можно сыграть Qc2, защищая... нет, точнее прикрывая коня c3. ",
    "Белые сыграют e3... стоп, лучше сначала Qc2. ",
])
def test_a_retraction_after_an_ellipsis_is_still_thinking_aloud(text):
    gate = SentenceGate(CheckContext.from_fens([NIMZO]))
    out = gate.feed(text) + gate.flush()
    assert any(o[1] == [META_ISSUE] for o in out)


# ── the evaluator is not the holder ──────────────────────────────────────────────────────────────────────────────────
ROOK_UP = "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1"  # White a rook up, White to move
QUEEN_DOWN = "3q2k1/5ppp/8/8/8/8/5PPP/6K1 w - - 0 1"  # White a queen down, White to move


@pytest.mark.parametrize("sentence", [
    "Ладья лишняя, и движок даёт белым выигранную позицию.",
    "У белых лишняя ладья, и движок даёт им огромный перевес.",
    "Engine gives White a winning advantage here.",
])
def test_the_engine_gives_the_verdict_to_the_side_in_the_dative(sentence):
    assert _evals(check_sentence(sentence, _eval_ctx(ROOK_UP, 6.1))) == []


@pytest.mark.parametrize("sentence, side", [
    ("Ладья лишняя, но движок даёт белым выигранную позицию.", "White"),
    ("У белых ферзя нет, и движок даёт им огромный перевес.", "White"),
    ("Движок даёт чёрным решающее преимущество.", "Black"),
])
def test_the_dative_holder_is_still_judged(sentence, side):
    ev = -8.7 if side == "White" else 8.7
    issues = _evals(check_sentence(sentence, _eval_ctx(QUEEN_DOWN if side == "White" else ROOK_UP, ev)))
    assert issues and (f"{side} is worse, not better" in issues[0] or f"{side} is not winning" in issues[0])


def test_the_engine_verdict_on_a_named_move_is_that_moves():
    ctx = _eval_ctx(ROOK_UP, 6.1)
    assert _evals(check_sentence("Зато h3 или ход ладьёй на d8 проигрывают: движок даёт чёрным решающий перевес.", ctx)) == []
    # the same words with no move named are about the board now
    assert _evals(check_sentence("Сейчас движок даёт чёрным решающий перевес.", _eval_ctx(ROOK_UP, 6.1)))


def test_a_side_owner_still_reads_as_before():
    assert _evals(check_sentence("У чёрных явный перевес.", _eval_ctx(ROOK_UP, 6.1)))
    assert _evals(check_sentence("Белые сейчас лучше.", _eval_ctx(QUEEN_DOWN, -8.7)))
    assert _evals(check_sentence("Белые сейчас лучше.", _eval_ctx(ROOK_UP, 6.1))) == []


# ── a name said as a variation ────────────────────────────────────────────────────────────────────────────────────────
ENGLISH_4N_FIANCHETTO = "c4 e5 Nc3 Nf6 Nf3 Nc6 g3 Bb4"
ENGLISH_3N = "c4 e5 Nc3 Nc6 Nf3"


@pytest.mark.parametrize("moves, sentence", [
    (ENGLISH_4N_FIANCHETTO, "Здесь у нас английское начало, система четырёх коней с фианкетто."),
    (ENGLISH_3N, "Это английское начало, система трёх коней."),
])
def test_a_variation_title_of_the_board_line_is_not_another_opening(moves, sentence):
    ctx = _game_ctx(moves, chess.WHITE)
    assert not [i for i in check_sentence(sentence, ctx) if "by the ECO book" in i]


@pytest.mark.parametrize("moves, sentence", [
    (ENGLISH_4N_FIANCHETTO, "Это дебют четырёх коней."),
    (ENGLISH_3N, "Это дебют трёх коней."),
])
def test_the_opening_itself_named_is_still_judged(moves, sentence):
    ctx = _game_ctx(moves, chess.WHITE)
    assert [i for i in check_sentence(sentence, ctx) if "by the ECO book" in i]


# ── to win a unit is to come out ahead ───────────────────────────────────────────────────────────────────────────────
# 1.e4 e5 2.Nf3 d6 3.d4 exd4 4.Qxd4: the student (Black) took on d4 and the queen took back
PHILIDOR_RECAPTURED = "e4 e5 Nf3 d6 d4 exd4 Qxd4 Nc6 Qd1"
# 1.d4 d5 2.c4 dxc4 3.e3 b5 4.a4 c6 5.axb5 cxb5 6.Qf3: the student (Black) took on c4 and kept the pawn
QGA_KEPT = "d4 d5 c4 dxc4 e3 b5 a4 c6 axb5 cxb5 Qf3"


@pytest.mark.parametrize("sentence", [
    "Ты выиграл пешку на d4.",
    "Ты выиграл пешку в центре.",
    "Пешка d4 тобой выиграна.",
])
def test_a_capture_taken_back_won_nothing(sentence):
    issues = check_sentence(sentence, _game_ctx(PHILIDOR_RECAPTURED, chess.BLACK))
    assert any("won the student no pawn" in i for i in issues), issues


def test_a_pawn_kept_is_won():
    assert not [i for i in check_sentence("Ты выиграл пешку на c4.", _game_ctx(QGA_KEPT, chess.BLACK)) if "won the" in i]


def test_an_exchange_still_going_on_is_unjudged():
    # the last move played is the capture: the recapture may still come
    ctx = _game_ctx("e4 e5 Nf3 d6 d4 exd4", chess.BLACK)
    assert not [i for i in check_sentence("Ты выиграл пешку на d4.", ctx) if "won the" in i]


def test_a_capture_told_as_taken_is_not_a_gain_claim():
    ctx = _game_ctx(PHILIDOR_RECAPTURED, chess.BLACK)
    assert not [i for i in check_sentence("Ты взял пешку на d4, а белые забрали обратно ферзём.", ctx) if "won the" in i]
