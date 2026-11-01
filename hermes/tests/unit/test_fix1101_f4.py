"""Fix 01.11 F4: the game record and the material, read as structure (review-miss / review-fp of 57bb4868).

material        a lead read from its parts (predicate class, quantity, side, word order, nouns), an explicit count
                compared exactly, «впереди на две пешки» also as points, equality with hedges
material now    in a game, the boards of the session's other games (and positions walked from them) never excuse
                a claim about the board now
free_capture    a free marker + a taker, loser or receiver verb; the capturer's from-square names the capture;
                «ничего не можешь взять в ответ» right after a capture that can be taken back
gave_up         a side, a loss verb in the past (any of the family), the unit in its case; a trade or an offer
                still under way, and a declined sacrifice, are not judged
student_capture the capturer's owner from a possessive, a colour adjective or genitive, a relative clause or the
                subject, compared with the game's record
"""
from __future__ import annotations

import sys
from pathlib import Path

import chess
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
from ctx_fixture import load_ctx, run_answer  # noqa: E402

from src import answer_check as ac  # noqa: E402

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "detect1031"

ST2 = "d4 e5 dxe5 Nc6 Nf3 Nf6 exf6"
ST2_5 = ST2 + " Be7 fxe7"
ST2_8 = ST2_5 + " d6 exd8=R+"
ST3 = "e4 e5 d4 d6 c3 Be7 Nf3 Nf6 Bc4 exd4 O-O Nxe4"  # Black is two pawns up
FRIED = "e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5 Nxf7 Kxf7 Qf3+ Ke6 Nc3"  # Black: a knight for a pawn (+2)


def _game(moves: str, student: str = "", fen: str = ""):
    sans = moves.split() if moves else None
    if sans:
        b = chess.Board()
        for m in sans:
            b.push_san(m)
        fen = b.fen()
    color = {"w": chess.WHITE, "b": chess.BLACK}.get(student)
    ctx = ac.CheckContext.from_fens([fen], [" ".join(sans)] if sans else [], student_color=color)
    if sans and color is not None:
        ctx.game_moves = sans
        first = 0 if color == chess.WHITE else 1
        ctx.game_engine_moves = [m for i, m in enumerate(sans) if i % 2 != first]
    ctx.language = "ru"
    return ctx


def _issues(sentence, moves, student="", before=()):
    return run_answer(list(before) + [sentence], _game(moves, student))[-1][1]


# ── material: the lead grammar ───────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "Ты отстаёшь на ферзя.",
    "У белых преимущество в ладью.",
    "Ты уступаешь по материалу целую ладью.",
    "Белые ведут по материалу на одну ладью.",
    "Перевес белых — одна фигура.",
    "Материально белые лучше на две пешки.",
    "Ты проигрываешь ладью по материалу.",
    "У белых лишняя ладья, но больше ничего.",
    "Материал почти равный.",
])
def test_a_lead_in_any_wording_is_judged(sentence):
    issues = _issues(sentence, ST2_8, "b")
    assert issues and "White has an extra 1 queen, 1 rook, 1 bishop, 1 knight" in issues[0], issues


@pytest.mark.parametrize("sentence,wrong", [
    ("У чёрных две лишние пешки.", False),
    ("Ты отстаёшь на две пешки.", False),
    ("Перевес чёрных — две пешки.", False),
    ("Материальный перевес у чёрных в две пешки.", False),
    ("Белые уступают по материалу две пешки.", False),
    ("По материалу чёрные ведут на две пешки.", False),
    ("Чёрные лучше по материалу на две пешки.", False),
    ("У чёрных больше пешек.", False),
    ("У чёрных лишняя пешка.", False),  # a bare «лишняя»: at least one — unjudged on purpose
    ("Материал: у чёрных одна лишняя пешка.", True),  # an explicit count is compared exactly
    ("У чёрных всего одна лишняя пешка.", True),
    ("Ты отстаёшь на одну пешку.", True),
    ("Перевес чёрных — пешка.", True),
    ("У белых больше пешек.", True),
    ("У тебя пешкой меньше.", True),
    ("Чёрные ведут по материалу на фигуру.", True),
])
def test_the_count_said_is_the_count_on_the_board(sentence, wrong):
    assert bool(_issues(sentence, ST3, "w")) == wrong, sentence


@pytest.mark.parametrize("sentence", [
    "Белые впереди в развитии на два темпа.",
    "У белых преимущество в пространстве.",
    "Движок даёт чёрным преимущество в одну пешку.",  # an evaluation in pawns
    "На ферзевом фланге у белых на пешку больше.",  # a majority, not the balance
    "У белых пешек меньше на две.",  # a count, not «на пешку меньше»
    "Белые давят больше на пешку f7.",  # «больше» is not the lead's predicate
    "У белых преимущество двух слонов.",  # the bishop pair
    "Материального равенства нет.",
    "Чёрные будут впереди на три пешки, если заберут c3.",
])
def test_what_is_not_a_material_lead_stays_unjudged(sentence):
    assert _issues(sentence, ST3, "w") == [], sentence


@pytest.mark.parametrize("sentence", [
    "Чёрные впереди на две пешки по материалу: конь за пешку.",
    "По очкам чёрные впереди на две пешки.",
    "Ты впереди на две пешки по материалу, но король на e6 под огнём.",
    "Белые позади на две пешки в пересчёте на очки.",
])
def test_a_lead_in_pawns_may_be_points(sentence):
    # review-fp 01.11 (Fried Liver, student Black): a knight for a pawn is +2 — the issue contradicted itself
    assert _issues(sentence, FRIED, "b") == [], sentence


def test_without_a_points_frame_pawns_are_pawns():
    # graded prod (tests/unit/test_answer_check.py: «Black is up two pawns already» with a knight for a pawn is wrong):
    # with no «по материалу / по очкам» or trade told, «на две пешки» counts pawns — and White has one pawn more
    assert _issues("Белые позади на две пешки, но у них атака.", FRIED, "b")


def test_a_compound_quantity_is_summed():
    assert _issues("Белые впереди на целую фигуру и пешку.", ST2 + " d6", "b") == []
    assert _issues("Белые впереди на ладью и слона.", ST2 + " d6", "b")


# ── material now: not another game's board ───────────────────────────────────────────────────────────────────────
def _row(rid):
    import json

    return json.loads((FIX / "rows" / f"{rid}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("sentence", [
    "Материал равный.",
    "Позиция после 1.e4 e5 2.d4 d6 3.c3 Be7 4.Nf3 Nf6 5.Bc4 exd4 6.O-O Nxe4: материал равный.",
    "После 6...Nxe4 ты отстаёшь на пешку.",
])
def test_another_games_board_does_not_excuse_the_material_now(sentence):
    r = _row("st3_10")
    issues = run_answer(list(r["prefix"]) + [sentence], load_ctx(r["ctx"]))[-1][1]
    assert issues and "Black has an extra 2 pawns" in issues[0], (sentence, issues)


def test_off_game_keys_and_following_positions():
    r = _row("st3_10")
    ctx = load_ctx(r["ctx"])
    off = ac._off_game_keys(ctx)
    assert ctx._key(ctx.current) not in off
    assert "r1bRk2r/ppp2ppp/2np4/8/8/5N2/PPP1PPPP/RNBQKB1R b" in off
    other = chess.Board("r1bqkb1r/pp3pp1/2nppn1p/2p1P3/2B5/3P1N1P/PPP2PP1/RNBQ1RK1 b kq - 0 7")
    assert not ac._can_follow(ctx.current, other)  # White has 6 pawns now, 8 there
    after = ctx.current.copy()
    after.push_san("cxd4")
    assert ac._can_follow(ctx.current, after)


# ── free_capture ─────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "Конь потерян даром.",
    "Ты потерял коня ни за что.",
    "Пешка e5 съела коня бесплатно.",  # the capturer's from-square names the capture
    "Конь отдан без всякой компенсации.",
    "Твой конь f6 погиб бесплатно.",
    "Белые выиграли целого коня без потерь.",
    "Конь достался белым даром.",
    "Белые забрали коня просто так, ничего не отдав.",
    "Белые выиграли фигуру за ничего.",
])
def test_a_capture_told_as_free_in_any_frame(sentence):
    issues = _issues(sentence, ST2, "b")
    assert issues and "4.exf6 is not free" in issues[0], (sentence, issues)


@pytest.mark.parametrize("sentence", [
    "Белые просто взяли коня, а ты ничего не можешь взять в ответ.",
    "Отыграть ничего нельзя: пешку f6 не взять.",
])
def test_no_way_back_right_after_a_capture_that_can_be_taken_back(sentence):
    issues = _issues(sentence, ST2, "b")
    assert issues and "can be taken back" in issues[0] and "gxf6" in issues[0], (sentence, issues)


@pytest.mark.parametrize("moves,student,sentence", [
    (ST2, "b", "Белые выиграли коня, но пешку f6 ты можешь забрать: gxf6 или Qxf6."),
    (ST2, "b", "Не спеши взять обратно: сначала посмотри на шахи."),
    (ST2, "b", "Ты ни за что не отдашь коня бесплатно."),
    (ST2, "b", "Белые просто так ничего не отдают."),
    ("e4 e5 Nf3 Nf6 Nxe5", "b", "Конь f3 съел пешку бесплатно."),
    ("e4 e5 Nf3 Nf6 Nxe5", "b", "Ты потерял пешку e5 даром."),
    ("e4 e5 f4 exf4", "w", "Белые отдали пешку f4 даром."),
    ("e4 e5 f4 exf4", "w", "Пешку f4 обратно не взять."),  # nothing takes f4 back with profit
    # a loss to come, and «ещё» another unit: not the game's last capture (corpus stand/st1)
    (ST2, "b", "Конь под боем, ферзь просто забирает его, и ты теряешь ещё фигуру без всякой компенсации."),
    (ST2, "b", "Ты потеряешь коня даром, если не уведёшь его."),
])
def test_free_and_no_way_back_true(moves, student, sentence):
    assert _issues(sentence, moves, student) == [], sentence


# ── gave_up ──────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "Чёрные пожертвовали центральную пешку ради линии c.",
    "Чёрные уже разменяли c-пешку на центральную.",
    "Чёрные уступили тебе центральную пешку.",
    "Чёрные остались без центральной пешки.",
    "Чёрные пожертвовали пешку c5.",
    "Соперник отдал пешку ради быстрого развития.",
    "Чёрные отдали пешку c за твою пешку d.",
])
def test_a_loss_in_any_verb_of_the_family(sentence):
    issues = _issues(sentence, "e4 c5", "w")
    assert issues and "Black (the engine) has lost no pawn" in issues[0], (sentence, issues)


@pytest.mark.parametrize("moves,student,sentence", [
    ("e4 c5", "w", "Чёрные отказались от центральной пешки."),  # declined or gave up: unjudged
    ("e4 c5", "w", "Чёрные отдали тебе центр."),  # no unit of material
    ("e4 c5", "w", "Чёрные не отдали пешку."),
    ("e4 c5", "w", "Ты чуть не потерял пешку."),
    ("e4 c5 d4 cxd4 Nf3", "w", "Чёрные отдали пешку c за пешку d."),  # the trade is under way
    ("e4 c5 d4 cxd4 Nf3", "w", "Чёрные разменяли c-пешку на центральную."),
    ("e4 e5 f4", "w", "Белые пожертвовали пешку f4 ради атаки."),  # on offer, not taken yet
    ("e4 c5 d4 cxd4 c3", "w", "Белые пожертвовали пешку, но чёрные её не взяли."),
    ("e4 e5 f4 exf4", "w", "Ты отдал пешку f4 ради быстрого развития."),
    (ST2_8, "b", "Ты остался без ферзя."),
])
def test_a_loss_that_is_not_one_or_is_in_the_record(moves, student, sentence):
    assert _issues(sentence, moves, student) == [], sentence


def test_a_count_of_losses():
    issues = _issues("Ты потерял две пешки.", ST2_8, "b")
    assert issues and "only 1 pawn, not 2" in issues[0]


# ── student_capture ──────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "Be7 — и твоя пешка f6 забрала слона на e7.",
    "Be7 — и ты сам срубил слона пешкой f6.",
    "Be7 — и пешка, которую ты двинул на f6, взяла слона на e7.",
    "Be7 — и чёрная пешка взяла слона на e7.",
    "Be7 — пешка чёрных f6 побила слона e7.",
])
def test_the_capturers_owner_in_any_form(sentence):
    issues = _issues(sentence, ST2_5, "b")
    assert any("5.fxe7 was White's (the engine's) capture" in i for i in issues), (sentence, issues)


@pytest.mark.parametrize("moves,student,sentence", [
    (ST2_5, "b", "Be7 — и белые сразу бьют по нему пешкой: 5.fxe7, их пешка с f6 забрала твоего слона на e7."),
    (ST2_5, "b", "Белая пешка с f6 взяла слона на e7."),
    (ST2_5, "b", "Белые взяли коня на f6."),
    (ST2, "w", "Твоя пешка с e5 забрала коня на f6."),
    (ST2, "w", "Пешка e5 взяла коня."),  # no owner said
    ("e4 c5 d4 cxd4 Nf3", "w", "Чёрные взяли пешку на d4."),
])
def test_a_capture_with_its_true_owner_passes(moves, student, sentence):
    assert _issues(sentence, moves, student) == [], sentence


def test_a_colour_that_did_not_capture():
    issues = _issues("Белые взяли пешку на d4.", "e4 c5 d4 cxd4 Nf3", "w")
    assert issues and "2...cxd4 was Black's (the engine's) capture, not White's" in issues[0]


def test_the_capture_record_names_its_squares():
    from src.game_record import captures

    cap = captures(_game(ST2, "b"))[-1]
    assert (chess.square_name(cap.from_square), chess.square_name(cap.to_square)) == ("e5", "f6")
