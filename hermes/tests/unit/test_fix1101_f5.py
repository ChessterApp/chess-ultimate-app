"""F5 (01.11): plans, blocks and lines — read by structure, judged on the board the sentence is about.

No engine here: the proposal tests check which move a sentence hands the engine (src/answer_check.proposed_move), the
block and line tests check the sync verdicts (check_sentence). Positive cases are false sentences (or advice the engine
must see), negative ones are true sentences that must pass untouched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import chess
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "support"))

from ctx_fixture import load_ctx  # noqa: E402

from src.answer_check import CheckContext, check_sentence, proposed_move  # noqa: E402

ROWS = HERE / "fixtures" / "detect1031" / "rows"


def _row_ctx(row: str) -> CheckContext:
    r = json.loads((ROWS / f"{row}.json").read_text(encoding="utf-8"))
    ctx = load_ctx(r["ctx"])
    for p in r["prefix"]:
        check_sentence(p, ctx)
    return ctx


def _moves_ctx(moves: str, student=None, game=None) -> CheckContext:
    b = chess.Board()
    for m in moves.split():
        b.push_san(m)
    ctx = CheckContext.from_fens([b.fen()], [moves], student_color=student)
    if student is not None and (game is None or game):
        ctx.game_moves = moves.split()
        first = 0 if student == chess.WHITE else 1
        ctx.game_engine_moves = [m for i, m in enumerate(moves.split()) if i % 2 != first]
    ctx.language = "ru"
    return ctx


def _proposed(ctx, sentence):
    check_sentence(sentence, ctx)
    found = proposed_move(sentence, ctx)
    return found[2] if found else None


TAIMANOV = "e4 c5 Nf3 e6 d4 cxd4 Nxd4 Nc6 Nc3 a6"


# ── plan_place / propose_vocab: the move a plan or an evaluation hands the engine ──────────────────────────────────
@pytest.mark.parametrize("sentence, san", [
    ("План чёрных: Nf6, затем c5.", "Nf6"),
    ("План за чёрных прост: Nf6 давит на e4, потом ...c5.", "Nf6"),
    ("Чёрные готовят Nf6 и Bg4.", "Nf6"),
    ("Чёрные ставят коня на f6, ферзя на b6 и играют c5.", "Nf6"),
    ("Чёрные развивают коня на f6.", "Nf6"),
    ("Конь g8 идёт на f6.", "Nf6"),
    ("В этом варианте чёрный конь обычно идёт на f6.", "Nf6"),
    ("Сначала Nf6, потом e6.", "Nf6"),
    ("Сначала e6, потом Nf6.", "e6"),
    ("Хорошо сыграть ...Nf6.", "Nf6"),
    ("Чёрным полезно Кf6.", "Nf6"),
    ("За чёрных логичен ход конём на f6.", "Nf6"),
    ("Типичная идея за чёрных — конь f6.", "Nf6"),
    ("Главная задача чёрных — подорвать центр ходом c5.", "c5"),
])
def test_plan_frames_hand_the_first_move_to_the_engine(sentence, san):
    assert _proposed(_row_ctx("name-caro-adv"), sentence) == san


@pytest.mark.parametrize("sentence, san", [
    ("Пока развивай фигуры: Qe2 и Be3.", "Qe2"),
    ("Продолжай развитие ходом Qe2.", "Qe2"),
    ("Готовь длинную рокировку: Qe2, Be3, 0-0-0.", "Qe2"),
    ("Дальше логично Qe2.", "Qe2"),
    ("Неплохо Qe2, чтобы прикрыть f1.", "Qe2"),
    ("Твой следующий ход — Qe2.", "Qe2"),
    ("Ферзь на e2 — лучший вариант.", "Qe2"),
])
def test_vocabulary_frames_hand_the_move_to_the_engine(sentence, san):
    assert _proposed(_row_ctx("castle-00"), sentence) == san


@pytest.mark.parametrize("sentence", [
    # a precondition or a later-word puts the placement off (review-fp plan-00, plan-01 — true sentences cut by Nd5)
    "Типичный план за белых — конь на d5, но только после того, как пешка e6 уйдёт.",
    "Со временем конь встанет на d5.",
    "План белых — конь на d5, когда пешка e6 уйдёт.",
    "Если чёрные сыграют d6, конь пойдёт на d5.",
    "Белые не ставят коня на d5: пешка e6 его сразу прогонит.",
    "План белых был прост: конь на d5.",
    "План чёрных — конь на d4.",  # the other side's plan
    "Почему план белых — конь на d5?",
])
def test_deferred_or_conditional_plans_propose_nothing_now(sentence):
    assert _proposed(_moves_ctx(TAIMANOV), sentence) is None


def test_but_first_names_the_move_now():
    ctx = _moves_ctx(TAIMANOV)
    assert _proposed(ctx, "Идея за белых: конь на d5 — но сначала надо подготовить это ходом f4 и f5.") == "f4"


@pytest.mark.parametrize("moves, sentence, san", [
    # a move denied to the other side is not advice (review-fp prevents rows, cut on main by the engine)
    ("e4 c6 d4", "2.d4 — занимая центр и не давая чёрным спокойно сыграть e5.", None),
    ("e4 c6 d4", "2.d4, not letting Black play e5 for free.", None),
    ("e4 e5 Bc4 Nc6 Qh5", "Ферзь h5 уже стоит, не давая чёрным поставить коня на f6 из-за мата на f7.", None),
    ("d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3", "6.Nf3, не давая чёрным сыграть e5.", None),
    # a move marked «?» is the doubtful one; the advice is the one after «лучше»
    ("e4 e5 Nc3 Nf6 d3 Bb4", "Можно и увести короля из-под связки — Kd2? Нет, лучше Bd2.", "Bd2"),
    # a possibility outranked in the same sentence, and the past, recommend nothing now
    ("e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d4 exd4 cxd4 Bb4+", "Можно закрыться и ферзём на d2, но слон лучше.", None),
    ("e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5 Nxf7 Kxf7 Qf3+ Ke6 Nc3", "На 7.Qf3+ можно было закрыться ферзём — Qf6.", None),
])
def test_proposal_words_that_propose_nothing_now(moves, sentence, san):
    assert _proposed(_moves_ctx(moves), sentence) == san


def test_a_plan_told_as_the_games_own_next_move_is_narration():
    ctx = _moves_ctx("e4 c6 d4 d5 e5")
    ctx.add_line("e4 c6 d4 d5 e5 Bf5")
    assert _proposed(ctx, "Чёрные ставят слона на f5.") is None


def test_a_still_wanted_proposal_is_still_read():
    ctx = _moves_ctx("e4 c6 d4 d5 e5")
    assert _proposed(ctx, "Чтобы не дать белым сыграть c4, сыграй c5.") == "c5"
    assert _proposed(ctx, "Сыграй c5, а потом Nc6.") == "c5"


# ── block_kind: a block of the check, named or not ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "Шах можно перекрыть.",
    "Закройся слоном.",
    "Ты можешь перекрыть шах конём c6.",
    "Встань конём между ладьёй и королём.",
    "Варианты: уйти королём или закрыться.",
    "Блокируй шах конём.",
    "Nxd8 — это заслон от шаха.",
    "Шах можно закрыть ходом Nxd8.",
    "Закройся от шаха слоном: Bd7.",
    "Закрыться от шаха можно ходом Bd7.",
    "Лучший ответ — Qd7.",
])
def test_a_contact_check_cannot_be_blocked(sentence):
    assert check_sentence(sentence, _row_ctx("st2_8-block"))


@pytest.mark.parametrize("sentence", [
    "У тебя три хода: взять ладью королём или конём (Kxd8, Nxd8) или отойти Ke7.",
    "Закрыться нечем, остаётся Kxd8.",
    "Закрыться нельзя: шах даёт ладья вплотную.",
    "Перекрыть шах нельзя, бери ладью: Kxd8.",
])
def test_true_sentences_about_the_contact_check_pass(sentence):
    assert check_sentence(sentence, _row_ctx("st2_8-block")) == []


BB5_CHECK = "e4 e5 Nf3 d6 Bb5+"


@pytest.mark.parametrize("sentence, wrong", [
    ("Закройся слоном: Bd7.", False),
    ("Закройся конём.", False),
    ("Шах можно перекрыть пешкой c6.", False),
    ("Перекрой шах ферзём на d7.", False),
    ("Закройся ладьёй.", True),
    ("Перекрыть шах можно только слоном.", True),
    ("Закройся конём на c6.", False),
    ("Закройся ферзём на e7.", True),
])
def test_blocks_against_the_board_with_blocks(sentence, wrong):
    assert bool(check_sentence(sentence, _moves_ctx(BB5_CHECK))) is wrong


# ── lines: the recapture and the next ply judged where the line stands ─────────────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "Тогда после Nxd4 Nxd4 exd4 Qxd4 белый ферзь встаёт в центр с темпом.",
    "Тогда конь c6 уходит на d4 и после Nxd4 exd4 Qxd4 размен выгоден белым.",
    "Тогда коню c6 некуда возвращаться: после Nxd4 exd4 белые сразу играют Qxd4.",
    "После 3...Nxd4 4.Nxd4 exd4 5.Qxd4 белые лучше.",
])
def test_recaptures_inside_a_run_are_played_from_its_start(sentence):
    issues = check_sentence(sentence, _row_ctx("can-scotch"))
    assert not any("is impossible" in i for i in issues), issues


def test_a_recapture_with_no_pawn_is_still_impossible():
    ctx = _moves_ctx("e4 e5 Nf3 Nc6 Bc4 Bc5 O-O Nf6 d3 d6 Be3")
    issues = check_sentence("Чёрные бьют Bxe3, а ты берёшь dxe3.", ctx)
    assert any("dxe3 is impossible" in i for i in issues), issues


@pytest.mark.parametrize("sentence", [
    "После 3...Nxd4 4.d5 конь на c6 под ударом.",
    "3...Nxd4 4.d5 — и конь c6 под ударом.",
    "После 3...Nxd4 белые играют 4.d5.",
])
def test_the_next_ply_of_a_line_must_be_legal_after_it(sentence):
    issues = check_sentence(sentence, _row_ctx("can-scotch"))
    assert any("4.d5 is impossible" in i for i in issues), issues


def test_a_quoted_move_is_followed_not_skipped():
    ctx = _moves_ctx("e4 e5 Nf3 Nc6 d4")
    ctx.quoted = {"Nxd4"}
    issues = check_sentence("После 3...Nxd4 4.d5 конь на c6 под ударом.", ctx)
    assert any("4.d5 is impossible" in i for i in issues), issues
    ctx = _moves_ctx("e4 e5 Nf3 Nc6 d4")
    ctx.quoted = {"Nxd4"}
    assert not any("impossible" in i for i in check_sentence("После 3...Nxd4 4.Nxd4 exd4 белые берут 5.Qxd4.", ctx))


# ── the /learn lesson tutor is the team's: its reading stays as it was on 31.10 ────────────────────────────────────
def test_the_lesson_surface_keeps_the_old_reading():
    ctx = _moves_ctx("e4 c6 d4")
    ctx.relation_surface = "lesson"
    assert _proposed(ctx, "2.d4 — занимая центр и не давая чёрным спокойно сыграть e5.") == "e5"
    ctx = _row_ctx("name-caro-adv")
    ctx.relation_surface = "lesson"
    assert _proposed(ctx, "План чёрных: Nf6, затем c5.") is None
    ctx = _row_ctx("st2_8-block")
    ctx.relation_surface = "lesson"
    assert check_sentence("Шах можно перекрыть.", ctx) == []


# ── wordings outside the reviewers' sets: the structure, not the graded words ─────────────────────────────────────
@pytest.mark.parametrize("sentence, san", [
    ("Идея чёрных — Nf6 с давлением на e4.", "Nf6"),
    ("Задача чёрных: вывести коня на f6.", "Nf6"),
    ("Чёрные хотят поставить коня на f6.", "Nf6"),
    ("Конь с g8 должен идти на f6.", "Nf6"),
    ("Ход Nf6 здесь вполне логичен.", "Nf6"),
    ("Сперва Nf6, а уже потом c5.", "Nf6"),
    ("Позже, когда пешка e5 будет разменяна, конь пойдёт на f6.", None),
    ("Чёрные никогда не ставят коня на f6 в этом варианте.", None),
    ("В будущем конь может перейти на f5 через e7.", None),
])
def test_unseen_plan_wordings(sentence, san):
    assert _proposed(_row_ctx("name-caro-adv"), sentence) == san


def test_a_plan_after_a_move_told_in_words_is_not_advice_now():
    ctx = _moves_ctx("e4 e5 f4")
    assert _proposed(ctx, "Играешь и забираешь пешку f4: она ничем не защищена, а взамен у тебя появляется "
                          "сильная идея — ферзь на h4 с шахом.") is None


@pytest.mark.parametrize("sentence, wrong", [
    ("Шах можно перекрыть, но не ладьёй.", False),
    ("Закройся конём или ладьёй.", False),
    ("Подумай, куда увести ферзя, чтобы заодно прикрыть своего короля.", False),
])
def test_block_alternatives_negations_and_hints(sentence, wrong):
    assert bool(check_sentence(sentence, _moves_ctx(BB5_CHECK))) is wrong


def test_a_denial_far_after_the_block_word_is_read():
    """«…король обязан отойти, но закрыться или съесть слона он не может» (eval row, a double check): a denial, no claim."""
    from src.answer_check import _block_claims

    assert _block_claims("король обязан отойти, но закрыться или съесть слона он не может.") == []
    assert _block_claims("закрыться ферзём не выйдет.") == []


# ── true sentences of the corpora (validate.sh, 01.11) that an earlier draft cut ──────────────────────────────────
@pytest.mark.parametrize("fen, sentence", [
    # a piece already standing between, described in the present — not a block to make
    ("5rk1/6q1/8/8/8/8/8/5QK1 w - - 0 1", "Ключ в том, что ферзь белых сам связан: он прикрывает своего короля от шахов по линии f."),
    ("8/8/8/8/4N3/5q2/6K1/8 w - - 0 1", "Смотри: Qf3+ бьёт и по королю на g2, и по коню e4, а заодно перекрывает королю выход."),
    # a pawn shield is not a block
    ("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1", "Ладья идёт на h4 — король на h7 зажат своим же пешечным заслоном, и защиты нет."),
    # a line from the start told with Black's first move: not judged after a board whose side was changed
    (chess.STARTING_FEN, "**Оттеснение** — 1...a6 2.Ba4 b5: пешки прогоняют слона с диагонали."),
])
def test_corpus_true_sentences_pass(fen, sentence):
    assert check_sentence(sentence, CheckContext.from_fens([fen])) == []


def test_a_block_after_a_told_line_is_judged_only_where_the_line_stands():
    # the board now is in check from the rook on h2; the block is told after Rc8+ … Qb1+, which the walk cannot reach
    ctx = CheckContext.from_fens(["6k1/5pp1/7p/8/8/8/7r/2R1Q1K1 w - - 0 1"])
    ctx.add("2R3k1/5pp1/7p/8/8/8/6Kr/4Q3 b - - 0 1")
    assert not any("g6" in i for i in check_sentence(
        "Белые цепляются за счёт шахов: Rc8+ загоняет твоего короля на h7, потом Qb1+ — и тут спокойно закройся g6.", ctx))
