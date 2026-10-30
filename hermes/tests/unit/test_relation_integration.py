"""The relation checker after the merge of WP-A/B/C/D (integration, 30.10): the classes of false flags the review of
the corpus found, each closed by a mechanism, and the real errors next to them that must stay caught.

Every test runs whole answers sentence by sentence through ``check_sentence`` in shadow mode (the relation issues are
recorded and nothing is cut, so the state goes on as on the page) and looks at what the relation checker recorded.
"""
import json
from pathlib import Path

import chess
import pytest

from src import answer_check_relations as acr
from src import claim_grammar, claim_judge, config
from src.answer_check import CheckContext, _split_sentences, check_sentence

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "relations"


def _sentences(text):
    done, rest = _split_sentences(text + " ")
    return [s for s in done + [rest] if s.strip()]


def _flags(text, fen, shown=None, game=None, question="", student=None):
    """{sentence: relation issues} of *text* on its board, the answer read in order."""
    lines = [" ".join(game)] if game else []
    ctx = CheckContext.from_fens([fen, shown], lines=lines, question=question, student_color=student)
    if game:
        ctx.game_moves = list(game)
    out = {}
    for s in _sentences(text):
        before = len(ctx.relation_shadow)
        check_sentence(s, ctx)
        out[s.strip()] = [i for _, issues in ctx.relation_shadow[before:] for i in issues]
    return out


@pytest.fixture(autouse=True)
def _shadow(monkeypatch):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "shadow")
    assert acr.mode() == "shadow"


def _flagged(flags, fragment):
    got = [v for k, v in flags.items() if fragment in k]
    assert got, f"no sentence holds {fragment!r}: {list(flags)}"
    return got[0]


# ── the line a sentence without a claim tells is the scene of the next ─────────────────────────────────────────────
def test_the_sentence_after_a_told_move_may_describe_the_board_after_it():
    flags = _flags("Да, есть — но только одна: **Nc7+**. Это вилка: конь бьёт и короля на e8, и ладью на a8.",
                   "r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1", question="Есть ли здесь вилка?")
    assert _flagged(flags, "Это вилка") == []


def test_choices_are_not_a_line():
    # «Крg5 или Л:h7» are two replies, not a line: the next sentence's «Л:h7, то следует Кg8+» is played from the board
    # after 1.Rh7+, and its fork is true.
    text = ("Первый ход — **Лh7+!** Это шах и одновременно вилка: ладья h7 бьёт и короля h6, и ладью h8. "
            "У чёрных всего два ответа: Крg5 или Л:h7. "
            "Вот в чём соль: если чёрные бьют ладью — Л:h7, то следует **Кg8+** (снова вилка — конь бьёт короля).")
    flags = _flags(text, "7r/2R5/5Npk/8/3B2P1/5pK1/3q3P/8 w - - 0 1",
                   question="Задача из урока «Мат в 3 хода». Какой здесь первый ход и почему?")
    assert _flagged(flags, "Вот в чём соль") == []


def test_a_false_claim_after_a_told_line_is_still_caught():
    text = ("Мат в 3 начинается с жертвы ферзя: **1. Фxh7+!** "
            "Чёрные обязаны взять — у короля нет другого хода: **1...Крxh7**. "
            "После Kxh7 ты играешь Лh3+ — и поле h6 защищено твоим ферзём.")
    flags = _flags(text, "r3nr1k/1bp1b1pp/4Pp2/p1pq1N1Q/N2p1B2/6R1/PPP2PPP/R5K1 w - - 0 1",
                   question="Задача из урока «Мат в 3 хода». Какой здесь первый ход и почему?")
    assert _flagged(flags, "защищено твоим ферзём")  # the queen is gone: nothing of White's on h6's lines


# ── a lesson's example board: a move "already on it" is no reading of the words ────────────────────────────────────
def test_moves_already_on_a_lesson_example_board_are_not_judged_there():
    text = ("На доске пример из вашей программы: чёрные напали на коня b1. Сравните варианты за белых. "
            "Лучше всего Кс3: конь и спасён, и выведен на хорошую клетку, и сам нападает на слона.")
    flags = _flags(text, chess.STARTING_FEN, shown="r2q1rk1/ppp2ppp/2npbn2/2b1p1B1/4P3/1BNP1N2/PPP2PPP/R2Q1RK1 b - - 0 1",
                   question="Объясни тему «Польза ходов» и покажи пример.")
    assert _flagged(flags, "Лучше всего Кс3") == []


# ── an object the move the turn is about puts there (en passant) ───────────────────────────────────────────────────
def test_an_object_one_legal_move_puts_there_is_an_alternative():
    flags = _flags("Но подумай: пешку на d6 никто не защищает, и чёрные спокойно забирают её ферзём.",
                   "rnbqkbnr/1pp1pppp/p7/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3",
                   question="Можно ли взять на проходе?")
    assert _flagged(flags, "никто не защищает") == []


def test_a_told_move_does_not_bring_its_object_in():
    # x-wc2021-g6: the knight reached g7 a move later — a move told in the sentence places the pieces itself, so the
    # implicit move of an object is read only when the sentence tells none.
    a = json.loads((FIX / "triage.json").read_text())["answers"]["x-wc2021-g6"]
    ctx = CheckContext.from_fens([a["fen"], a["shown"]], lines=a["lines"], question=a["question"])
    check_sentence("Чёрные только что сыграли 135...Qg1, напав на коня g7, но ферзь уже не спасает.", ctx)
    assert [i for _, issues in ctx.relation_shadow for i in issues], "x-wc2021-g6 must stay caught"


# ── a piece the claim names is gone from the board now: the game's last positions ──────────────────────────────────
def test_a_present_claim_about_a_piece_just_gone_reads_the_last_positions():
    game = ["e4", "c5", "Nf3", "Nc6", "Bc4", "e6", "O-O", "d5", "d3", "dxc4"]
    b = chess.Board()
    for m in game:
        b.push_san(m)
    flags = _flags("Смотри, что произошло: ты поставил пешку на d3, чтобы защитить e4, но забыл, что его пешка d5 бьёт и "
                   "по e4, и по твоему слону.", b.fen(), game=game, question="d3", student=chess.WHITE)
    assert _flagged(flags, "его пешка d5") == []


# ── a pronoun read as a piece of the other side ───────────────────────────────────────────────────────────────────
def test_a_defender_of_the_other_side_means_the_pronoun_is_misread():
    text = ("Смотри на чёрного слона на **d7**. Его атакуют сразу **две** белые фигуры:\n- слон с **b5** "
            "(по диагонали b5–c6–d7),\n- ладья с **d1** (по вертикали «d»).\n\n"
            "А защищают его только чёрная ладья с **f7** и ферзь с **d8**.")
    flags = _flags(text, "r2q2k1/pp1b1r1p/4p1p1/1B2Qp2/8/2P5/P4PPP/R2R2K1 w - - 0 1", question="Какой здесь первый ход?")
    assert _flagged(flags, "А защищают его") == []


# ── «прикрывать» is to shield too ──────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text, flagged", [
    ("Мой последний ход — 3...e6, пешка прикрыла поле f7 от твоего слона на c4.", False),
    ("Мой последний ход — 3...e6, слон на f8 прикрыл поле f7.", True),  # the bishop neither defends nor shields f7
])
def test_a_piece_on_the_enemy_line_covers_the_square(text, flagged):
    game = ["e4", "c5", "Nf3", "Nc6", "Bc4", "e6"]
    b = chess.Board()
    for m in game:
        b.push_san(m)
    got = _flagged(_flags(text, b.fen(), game=game, question="Что ты сейчас сыграл?", student=chess.WHITE),
                   "Мой последний ход")
    assert bool(got) is flagged, got


def test_shields_is_geometry():
    b = chess.Board("r1bqkbnr/pp1p1ppp/2n1p3/2p5/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4")
    assert claim_judge._shields(b, chess.E6, chess.F7)  # e6 stands alone on the c4–f7 diagonal
    assert not claim_judge._shields(b, chess.D7, chess.F7)


# ── «связан королём», a pin to an undefended equal piece ───────────────────────────────────────────────────────────
def test_tied_to_the_king_is_not_a_pin_claim():
    got = claim_grammar.extract("Пешка h3 связана королём.", {}, "ru")
    assert all(c.pos.at == "skip" for c in got)
    got = claim_grammar.extract("Конь c6 связан с королём e8.", {}, "ru")
    assert got and got[0].pos.at == "now"


def test_a_piece_in_front_of_an_undefended_equal_piece_is_pinned():
    b = chess.Board("1r4k1/3q1pp1/7p/pr1p4/8/4P1P1/Q4P1P/1R3BK1 w - - 0 2")  # after 1.Rxb5 Rxb5: Rb1 – Rb5 – Rb8
    assert claim_judge.pin_behind(b, chess.B1, chess.B5) == chess.B8
    b2 = chess.Board("1r1q2k1/5pp1/7p/pr1p4/8/4P1P1/Q4P1P/1R3BK1 w - - 0 2")  # the queen d8 guards b8: no pin
    assert claim_judge.pin_behind(b2, chess.B1, chess.B5) is None


def test_a_piece_named_by_the_square_it_just_left():
    text = "А почему не bxa7? Тогда чёрный слон бьёт твою пешку b6, и вместо мата ты сам отдаёшь инициативу."
    flags = _flags(text, "kbK5/p7/pP6/8/8/8/8/8 w - - 0 1",
                   question="Задача из урока «Мат пешкой». Какой здесь первый ход и почему?")
    assert _flagged(flags, "Тогда чёрный слон") == []


# ── the parser: a list of placements, routes, «откуда», recommendation cues ───────────────────────────────────────
def test_a_comma_list_of_placements_is_not_a_subject_list():
    got = claim_grammar.extract("Посмотри на доску: чёрный король на a8, ладья на f8, ферзь чёрных на f2 давит на b2.",
                                {}, "ru")
    assert [(c.subj.sq, c.subj.piece) for c in got] == [("f2", "Q")]
    got = claim_grammar.extract("Конь f3, слон c4 и ферзь d1 бьют по f7.", {}, "ru")
    assert {c.subj.sq for c in got} == {"f3", "c4", "d1"}


@pytest.mark.parametrize("text", [
    "Смотри: ферзь на d4 бьёт по королю через f2 и g4.",
    "Король успевает встать на b7 или b6, откуда поле a8 уже под контролем.",
])
def test_routes_and_imagined_places_are_skipped(text):
    assert all(c.pos.at == "skip" for c in claim_grammar.extract(text, {}, "ru"))


def test_a_recommendation_cue_makes_a_bare_square_the_move():
    got = claim_grammar.extract("Поэтому советую готовить короткую: сейчас сильнее всего b3 — пешка бьёт слона.", {}, "ru")
    assert got and got[0].pos.at == "after" and [m.to for m in got[0].pos.moves] == ["b3"]
    flags = _flags("Поэтому советую готовить короткую: сейчас сильнее всего b3 — пешка бьёт слона, и ему придётся уйти.",
                   "r2qk2r/ppp2ppp/2np1n2/4p3/2b1P3/2N2N2/PPP2PPP/R1BQK2R w KQkq - 0 8", question="А в длинную можно?")
    assert _flagged(flags, "сильнее всего b3") == []


# ── classes found by the existing answer-check tests once the parser and the judge ran together ───────────────────
def _game(moves, student, question=""):
    b = chess.Board()
    for m in moves:
        b.push_san(m)
    ctx = CheckContext.from_fens([b.fen()], question=question, student_color=student)
    ctx.game_moves = list(moves)
    return ctx


def _rel(sentence, ctx):
    before = len(ctx.relation_shadow)
    check_sentence(sentence, ctx)
    return [i for _, issues in ctx.relation_shadow[before:] for i in issues]


@pytest.mark.parametrize("moves, student, sentence", [
    # a motion with no square the parser could not place: the board after it is unknown
    ("d4 d5 c4 e6 Nc3 Nc6 Nf3 Nce7", chess.WHITE, "Мой конь на c6 отступил и прикрыл пешку d5."),
    ("e4 e5 Nf3 Nc6 Bc4 Nf6 d3 Bc5", chess.BLACK, "Мой конь встал на f6, вышел мой слон и напал на f2."),
    # a second motion with its own square is a second move
    ("e4 e5 Nf3 Nc6 Ng5 d6 Nf3", chess.BLACK, "Мой конь прыгнул на g5, вернулся на f3 и держит e5."),
    # a person or a side as the clause's subject
    ("e4 e5 Nf3 Bc5 Nc3 Bf8 d4", chess.WHITE, "Мой слон вернулся на f8, а ты тут же и напал на e5."),
    ("e4 Nf6 e5 Ng8 Bd3", chess.WHITE, "Мой конь отступил на g8, но белые, конечно, нацелились на h7."),
    # «ничем не прикрыт» with an exception or a side named
    ("e4 e5 Bc4 Nc6 Qh5", chess.BLACK, "Пешка на f7 ничем не прикрыта, если не считать короля."),
    ("e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nf6 Nc3 Bb4", chess.WHITE, "Конь на d4 ничем не прикрыт с фланга."),
    # «поддержал X в атаке на Y» joins the attack
    ("e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5", chess.BLACK, "Мой конь с f3 прыгнул на g5 и поддержал слона c4 в атаке на f7."),
])
def test_true_game_sentences_pass(moves, student, sentence):
    assert _rel(sentence, _game(moves.split(), student)) == []


def test_not_covered_means_no_shield_on_an_open_line():
    # the bishop b4 reaches c3 with nothing in between: «ничем не прикрыт со стороны слона» in the shield sense
    ctx = _game("e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nf6 Nc3 Bb4".split(), chess.WHITE)
    b = ctx.current
    assert claim_judge._open_line_to(b, chess.C3)
    assert not claim_judge._open_line_to(b, chess.E4)
    got = claim_grammar.extract("Конь на c3 ничем не прикрыт.", {}, "ru")
    assert got and got[0].kind == "cover"


PIANISSIMO = "r1bq1rk1/ppp2ppp/2np1n2/2b1p3/2B1P3/2PP1N2/PP3PPP/RNBQ1RK1 w - - 2 7"


@pytest.mark.parametrize("sentence", [
    "Конь с g8 сразу бьёт в e4.",  # the knight that came from g8 (f6)
    "The knight on f7 attacks the queen on d8 and the rook on h8, so Black takes it: 6...Kxf7.",  # a line not here
    "Удар конём на f7: конь на f7 бьёт ферзя d8 и ладью h8.",  # a blow in words no knight here can strike
])
def test_lines_told_about_another_position_pass(sentence):
    assert _rel(sentence, CheckContext.from_fens([PIANISSIMO], question="почему в жареной печени вилка?")) == []


def test_a_move_from_a_named_square_must_start_there():
    # «Nd5: конь с f3 прыгает на d5» — White's Nf3 cannot reach d5; Black's ...Nd5 is not what the words say
    issues = _rel("Ход, о котором речь — это Nd5: конь с f3 прыгает на d5 и бьёт ферзя.",
                  CheckContext.from_fens([PIANISSIMO]))
    assert not any("7...Nd5" in i for i in issues), issues


def test_every_named_piece_missing_is_another_position_but_one_missing_is_an_error():
    rook_g1 = "2r2rk1/2p3p1/pp1p1p2/2nR4/P3P2q/1PQ2P1P/2P2PK1/4R3 w - - 0 1"
    ctx = CheckContext.from_fens([rook_g1], student_color=chess.WHITE)
    assert _rel("Пешка e5 у чёрных висит, её держит только конь c6.", ctx) == []
    ctx = CheckContext.from_fens([rook_g1], student_color=chess.WHITE)
    assert _rel("Ладья на d5 бьёт пешку b7.", ctx)  # the rook stands there, the pawn does not


def test_nothing_defends_takes_the_object_after_the_verb():
    got = claim_grammar.extract("The pawn on a4 is attacked but nothing defends h4.", {}, "en")
    assert [o.sq for c in got if c.rel == "undefended" for o in c.objs] == ["h4"]


def test_a_counterfactual_question_leaves_missing_pieces_unjudged():
    ctx = CheckContext.from_fens(["2kr3r/1p2qp2/1bpp1n1p/p3p1p1/PPBnP3/2NP2BP/2P2PP1/R2Q1RK1 w - - 0 16"],
                                 question="А что было бы, если бы на 8-м ходу я взял слоном на g5 вместо Bg3?")
    assert _rel("Пешка h6 бьёт твоего слона g5, и уйти ему некуда.", ctx) == []


def test_a_question_about_an_earlier_move_leaves_pieces_gone_since_unjudged():
    # d4-move5 on the stand: the board is move 8, the question asks about move 5 and the PGN is not in the turn
    ctx = CheckContext.from_fens(["r1b1kbnr/pppp1Npp/8/8/4q3/5n2/PPPPBP1P/RNBQKR2 w Qkq - 2 8"],
                                 question="А что надо было играть на 5-м ходу?")
    assert _rel("Взять конём на f7 (5. Nxf7) — это жадность: вы забираете ладью, но ферзь чёрных на g5 уже целится в g2.",
                ctx) == []
