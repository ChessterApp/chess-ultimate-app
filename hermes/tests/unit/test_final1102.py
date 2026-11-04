"""The final fix of next-1031 (02.11): the held-out reviews' findings (review-fp2, review-miss2, review-wiring2).

  precision   the true sentences the held-out review found cut, by root cause (reply in check, the checker's square,
              the clause of «только», an exception after the cue, the pin's word order, the past, the start cue across
              «:» and «? Нет,», «не может пойти», a told move in words, a told line, a plan head, «трудно сыграть», a
              material gain read as the evaluation, the attacker named by a square, the square of a named move)
  mechanisms  the clause readers: capture / loss / trade events (src/capture_frames), the material balance
              (src/material_frames), the stop and the no-move lemma classes, the outcome predicate, the block lemmas,
              the necessity frames of mate, the book's names in Russian
  wiring      the lesson tutor keeps main's move check, the comment context's switch, cover_cause on comments, the
              hung process's slack, the idea confirm ahead of the candidates, #rest held back, the corpus path, the
              engine-only antidote
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import chess
import pytest

from src import config
from src.answer_check import CheckContext, check_sentence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
from ctx_fixture import load_ctx, run_answer  # noqa: E402

ROWS = Path(__file__).resolve().parents[1] / "fixtures" / "detect1031" / "rows"


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    monkeypatch.setattr(config, "STOCKFISH_POOL", False, raising=False)
    monkeypatch.setattr(config, "COACH_PRECOMPUTE", False, raising=False)
    monkeypatch.setattr(config, "COACH_MOVE_VERIFY", False, raising=False)
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW", raising=False)


def _ctx(moves: str = "", fen: str = None, student=None, game: bool = None) -> CheckContext:
    b = chess.Board(fen) if fen else chess.Board()
    mv = moves.split()
    for san in mv:
        b.push_san(san)
    ctx = CheckContext.from_fens([b.fen()], [" ".join(mv)] if mv and not fen else [], student_color=student)
    if mv and (game if game is not None else student is not None) and not fen:
        ctx.game_moves = mv
        first = 0 if student == chess.WHITE else 1
        ctx.game_engine_moves = [m for i, m in enumerate(mv) if i % 2 != first]
    ctx.language = "ru"
    return ctx


def _row(rid: str):
    import json

    r = json.loads((ROWS / f"{rid}.json").read_text(encoding="utf-8"))
    return r, load_ctx(r["ctx"])


def _row_issues(rid: str, sentence: str) -> list:
    r, ctx = _row(rid)
    return run_answer(list(r["prefix"]) + [sentence], ctx)[-1][1]


def test_every_touched_module_imports():
    # a module that fails to import is a detector silently off behind fail-open (endgame_claims did, mid-work)
    for name in ("endgame_claims", "claim_grammar", "claim_rules", "claim_scene", "claim_judge", "answer_check",
                 "answer_check_rules", "answer_check_openings", "capture_frames", "material_frames", "trade_claims",
                 "line_verdict", "hypothetical", "engine_pool", "engine_precompute", "game_record"):
        importlib.import_module(f"src.{name}")


# ── precision: the held-out true sentences (review-fp2 01.11) ────────────────────────────────────────────────────────
ITALIAN_CHECK = "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d4 exd4 cxd4 Bb4+"
SICILIAN_CHECK = "e4 c5 Nf3 d6 Bb5+"


@pytest.mark.parametrize("moves,student,sentence", [
    (SICILIAN_CHECK, chess.WHITE, "Ты дал шах; следующим ходом сыграй Nc3."),
    (SICILIAN_CHECK, chess.WHITE, "Дальше твой план — сыграть c3 и d4."),
    (SICILIAN_CHECK, chess.WHITE, "После его ответа лучше всего сыграть c3."),
    (ITALIAN_CHECK, chess.BLACK, "Ты дал шах слоном; дальше сыграй d5 и O-O."),
])
def test_a_proposal_to_the_side_that_gave_check_is_not_the_reply(moves, student, sentence):
    assert check_sentence(sentence, _ctx(moves, student=student)) == []


@pytest.mark.parametrize("sentence", [
    "Тебе шах от слона b4: закройся слоном d2, конём c3 или конём с b1.",
    "Против шаха с b4 — закройся слоном.",
    "Это шах слоном b4: закрыться можно слоном на d2.",
    "Шах от слона b4 — закрывайся, лучше всего слоном.",
])
def test_the_checkers_square_is_no_block_move(sentence):
    assert check_sentence(sentence, _ctx(ITALIAN_CHECK, student=chess.WHITE)) == []


@pytest.mark.parametrize("sentence", [
    "Слоном и конём мат возможен на любом поле края, но форсировать его можно только в углу цвета слона.",
    "Форсировать мат слоном и конём можно только в углу цвета слона, хотя сам мат бывает и на краю.",
])
def test_the_verb_of_only_is_read_in_its_own_clause(sentence):
    assert check_sentence(sentence, _ctx(fen="8/8/8/4k3/8/8/8/R3K3 w - - 0 1")) == []


@pytest.mark.parametrize("moves,sentence", [
    ("e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O h3",
     "Коню b1 в испанской долго некуда идти: d2 и c3 заняты пешками, свободно только a3."),
    ("d4 Nf6 c4 g6 Nc3 Bg7 e4 d6 f3 O-O Be3 e5 d5", "Ладья a1 заперта, если не считать b1 и c1."),
    ("e4 e5 Nf3 Nc6 Bc4 Bc5 d3 d6 Nc3 Bg4", "Связанный конь f3 не может уйти, не открыв ферзя d1."),
    ("d4 f5 c4 Nf6 g3 e6 Bg2 d5 Nf3 c6 O-O Bd6 b3 Qe7",
     "В начале партии ладья h1 никуда не может пойти: её закрывают конь g1 и пешка h2."),
])
def test_a_lock_with_an_exception_a_pin_or_its_blockers_named_is_not_judged(moves, sentence):
    assert check_sentence(sentence, _ctx(moves)) == []


@pytest.mark.parametrize("moves,sentence", [
    ("e4 e6 d4 d5 Nc3 Bb4", "Конь c3 связан с королём слоном b4."),
    ("e4 e5 Nf3 Nc6 Bc4 Bc5 d3 d6 Nc3 Bg4", "Конь f3 связан с ферзём слоном g4."),
    ("e4 e5 Nf3 Nc6 Bb5 d6", "Конь c6 связан с королём слоном b5."),
])
def test_a_pin_reads_its_agent_in_either_order(moves, sentence):
    assert check_sentence(sentence, _ctx(moves)) == []


@pytest.mark.parametrize("moves,student,sentence", [
    ("e4 e5 Nf3 Nc6 Nxe5 Nxe5", chess.WHITE, "Пешка e5 только выглядела беззащитной: её охранял конь c6."),
    ("e4 e5 Nf3 Nc6 Bc4 Bc5 b4 Bxb4 c3 Ba5 d4 exd4 O-O", chess.BLACK, "Ты взял пешку b4 бесплатно — её никто не защищал."),
    ("e4 e5 Nf3 Nc6 Bc4 Bc5 b4 Bxb4 c3 Ba5 d4 exd4 O-O", chess.BLACK, "Раньше пешку b4 никто не защищал."),
])
def test_the_past_is_judged_where_the_piece_stood(moves, student, sentence):
    assert check_sentence(sentence, _ctx(moves, student=student)) == []


ENGLISH_ATTACK = "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6 Be3 e5 Nb3 Be6"


@pytest.mark.parametrize("sentence", [
    "В исходной позиции король e1 окружён своими: d1, f1, d2, e2 и f2 заняты.",
    "В начальной позиции поле e4 пустое, а пешка e2 его уже контролирует? Нет, пешка e2 бьёт d3 и f3.",
    "До первого хода ферзь d1 не может пойти никуда.",
])
def test_the_start_cue_carries_through_the_sentence(sentence):
    assert check_sentence(sentence, _ctx(ENGLISH_ATTACK)) == []


@pytest.mark.parametrize("moves,fen,sentence", [
    ("", "8/8/8/8/8/1k6/8/r1K5 w - - 0 1", "Король не может пойти на d1: ладья a1 бьёт всю первую горизонталь."),
    ("d4 d5 c4 e6 Nc3 Nf6 Bg5", None, "После h6 Bh4 g5 слон уйдёт на g3 и будет держать поле e5."),
    ("d4 d5 c4 e6 Nc3 c5 cxd5 exd5 Nf3 Nc6 g3 Nf6 Bg2 Be7 O-O O-O", None, "План за белых: ладьи на c1 и d1, давление на пешку d5."),
    ("e4 e5 Nf3 Nc6 Bc4 Bc5 d3 d6 Nc3 Bg4", None, "Поле e2 между конём f3 и ферзём d1 пустое."),
    ("e4 e5 Nf3 Nc6 Bc4 Nf6 Nc3", None, "После 4...Nxe4 5.Nxe4 d5 пешка нападает на слона c4 и коня e4, и фигура возвращается."),
])
def test_the_words_board_is_the_one_judged(moves, fen, sentence):
    assert check_sentence(sentence, _ctx(moves, fen=fen)) == []


def test_the_idea_line_after_the_question_is_walked_whole():
    ctx = _ctx("e4 e5 Nf3 Nc6 Bc4 Nf6 Nc3")
    got = run_answer(["А почему не Nxe4?",
                      "Тогда конь f6 забирает пешку e4, а после Nxe4 d5 пешка нападает на слона c4 и коня e4."], ctx)
    assert got[-1][1] == []


def test_the_king_move_told_with_a_move_is_not_judged_before_it():
    ctx = _ctx(fen="8/8/8/8/2P5/4k3/8/K7 b - - 0 1", student=chess.BLACK)
    assert check_sentence("Твой король на e3 сразу нападает на пешку ходом Kd4.", ctx) == []


@pytest.mark.parametrize("rid,sentence", [
    ("st3_10", "Чёрные выиграли две пешки."),
    ("st3_10", "Чёрные выиграли у тебя две пешки, но позиция ещё играется."),
    ("castle-ru", "Слон c4 под ударом b3 уйдёт на a6 и сохранит контроль над f1."),
    ("op-show-ck-attack", "d4 не мешает чёрным сыграть d5: пешку d5 защищает c6."),
])
def test_review_miss2_true_controls_stay(rid, sentence):
    assert _row_issues(rid, sentence) == []


# ── mechanisms: the held-out false sentences, one or two per class ────────────────────────────────────────────────
@pytest.mark.parametrize("rid,sentence", [
    ("st2_5", "Слона e7 съела твоя пешка."),
    ("st2_5", "Слон e7 был взят чёрной пешкой."),
    ("st2_5", "Ход fxe7 сделал ты."),
    ("st1_1", "Чёрные расстались с d-пешкой."),
    ("st1_1", "Отдав центральную пешку, чёрные получили линию c."),
    ("st1_1", "Ценой центральной пешки чёрные открыли линию c."),
    ("x-wc2021-g6", "Ферзя белые пожертвовали за ладью и пешку."),
    ("x-wc2021-g6", "Непомнящий получил ферзя в обмен на ладью."),
    ("st2_8-material", "Белые опережают тебя на ладью."),
    ("st3_10", "Сейчас пешек поровну."),
    ("st3_10", "Ты потерял одну пешку."),
    ("op-show-ck-attack", "Слон f1 ходов не имеет."),
    ("op-show-ck-attack", "Чёрному ферзю не выйти из d8."),
    ("op-show-ck-eval", "Вариант 2.d4 d5 3.e5 оставляет слона c8 взаперти."),
    ("op-show-ck-attack", "Благодаря d4 чёрные лишены хода d5."),
    ("op-show-ck-attack", "Ходом d4 ты отнимаешь у чёрных d5."),
    ("castle-ru", "Ход b3 лишит слона контроля над f1."),
    ("castle-ru", "После b3 слон отступит, и королю уже ничто не мешает рокироваться."),
    ("lucena", "Чёрная ладья станет давать шахи вдоль вертикали d, как только король выйдет на c7."),
    ("st2_8-block", "Шах перекрывается конём."),
    ("st2_8-block", "Рокируйся: O-O."),
    ("two-knights", "Двум коням нужен угол для мата."),
    ("st1_2", "Это Калашников."),
    ("st2_4-attack", "Конь стал добычей на f6, ведь f6 под контролем пешки g7."),
    ("plan-caro-adv", "Конь b1 в связке, так что сначала Nd2."),
])
def test_review_miss2_false_sentences_are_cut(rid, sentence):
    assert _row_issues(rid, sentence), sentence


@pytest.mark.parametrize("rid,sentence", [
    ("st1_2", "Ход d6 не даёт белым сыграть d4."),
    ("op-show-ck-attack", "Ход c6 не даёт белым сыграть d4."),
])
def test_a_stopper_already_played_is_judged_on_the_board_it_made(rid, sentence):
    assert _row_issues(rid, sentence)


def test_a_stopper_from_the_start_is_a_line_not_a_diagram():
    assert check_sentence("Ход 1.d4 не даёт чёрным сыграть d5.", _ctx()) != []


def test_capture_frames_read_the_parts():
    from src.answer_check import _to_san
    from src.capture_frames import events

    def ev(s):
        return [(e.kind, e.who) for e in events(_to_san(s)[0])]

    assert ev("Слона e7 съела твоя пешка.") == [("take", "S")]
    assert ev("Чёрные расстались с d-пешкой.") == [("lose", "B")]
    assert ev("Ход fxe7 сделал ты.") == [("played", "S")]
    assert ev("Чёрные не брали пешку.") == []
    assert ev("Если ты возьмёшь коня, белые отдадут ферзя.") == []


def test_material_frames_read_the_parts():
    from src.material_frames import read

    def mc(s):
        return [(c.kind, c.who, c.more, c.points) for c in read(s)]

    assert mc("Белые опережают тебя на ладью.") == [("lead", "W", True, 5)]
    assert mc("Разница в материале — ферзь.") == [("diff", "", True, 9)]
    assert mc("Белые впереди.") == []  # no amount, no material word: maybe the evaluation
    assert mc("На ферзевом фланге у белых больше пешек.") == []  # a majority


# ── wiring ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_lesson_tutor_keeps_mains_move_check(monkeypatch):
    from src import board_rules, hypothetical

    board = chess.Board("1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1")
    monkeypatch.setattr(board_rules, "tablebase", lambda b: {"keeping": ["Rd1+"]})
    assert hypothetical._tablebase_keeps(board, "Rd1+") is True
    assert hypothetical.main_rules(hypothetical._tablebase_keeps)(board, "Rd1+") is False
    assert hypothetical.main_rules(hypothetical._ending_unproven)(board, 6.1, 4.3) is False
    monkeypatch.setenv("COACH_DETECTORS_OFF", "tablebase_keeps")
    assert hypothetical._tablebase_keeps(board, "Rd1+") is False


def test_cover_cause_reads_the_record_on_a_comment():
    ctx = CheckContext.from_fens()
    ctx.relation_surface = "game"
    assert config.detector_mode("cover_cause", ctx) == config.detector_mode("cover_cause")
    assert config.detector_mode("pin_escape", ctx) == "shadow"
    assert config.detector_mode("comment_record") == "on"


def test_a_search_with_a_deadline_reads_little_past_it():
    from src import engine_pool

    got = engine_pool._read_timeout("depth 17 movetime 1000", None, __import__("time").monotonic() + 1.0)
    assert got <= 1.0 + engine_pool.DEADLINE_SLACK_S / 2 + 0.01


def test_the_students_idea_confirm_goes_before_the_candidates():
    from src import engine_precompute as ep

    assert ep.LEVEL_IDEA < ep.LEVEL_CHECK < ep.LEVEL_CONFIRM < ep.LEVEL_BOARD
    task = ep._Task("k#rest", __import__("src.engine_pool", fromlist=["Job"]).Job("rest"), [("rest_move", None)], 0)
    task.not_before = __import__("time").monotonic() + 60
    assert not ep._startable(task)
    assert "rest_move" not in ep.PARALLEL_STEPS


def test_the_relation_corpus_is_found_from_a_worktree():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import eval_relations

    assert eval_relations.PROD_RUN.name == "prod-run"


def test_an_antidote_only_the_engine_line_carries_is_not_lost():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import eval_prevent

    msg = "Board facts.\n[Engine] fen — White to move. Best: d4 (+0.26; line d4 d5 e5 Bf5).\nMore."
    assert "Bf5" not in eval_prevent._without_engine(msg)
    assert "Board facts." in eval_prevent._without_engine(msg)


def test_cover_cause_cuts_a_move_comment_by_the_record():
    r, ctx = _row("st2_4-attack")
    ctx.relation_surface = "game"
    got = run_answer(["Конь стал добычей на f6, ведь f6 под контролем пешки g7."], ctx)[-1][1]
    assert got, "cover_cause follows the record on a move comment"


@pytest.mark.parametrize("sentence,cut", [
    ("После 3...Nf6 у белых уже был лишний конь.", True),
    ("После 2.dxe5 у белых была лишняя пешка.", False),
])
def test_material_at_a_numbered_move_of_the_record(sentence, cut):
    assert bool(_row_issues("st2_4-eval", sentence)) is cut


def test_a_past_anchor_is_the_end_of_the_line_it_opens():
    ctx = _ctx("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6", student=chess.WHITE)
    assert check_sentence("После 3.d4 cxd4 у чёрных была лишняя пешка, но 4.Nxd4 её вернул.", ctx) == []


@pytest.mark.parametrize("sentence,cut", [
    ("Слон c4 под ударом b3 уйдёт, и поле f1 станет безопасным.", True),
    ("После b3 слон c4 уйдёт, и f1 окажется в безопасности.", True),
    ("После b3 слон c4 уйдёт на d3, и поле f1 станет безопасным.", True),  # d3 is on the f1 diagonal
    ("После b3 слон c4 уйдёт на d5, и поле f1 станет безопасным.", False),
    ("После b3 слон c4 уйдёт, но поле f1 всё равно не станет безопасным.", False),
])
def test_a_safe_square_is_a_square_the_chased_piece_no_longer_covers(sentence, cut):
    assert bool(_row_issues("castle-ru", sentence)) is cut, sentence
