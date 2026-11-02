"""verify1102 K1: material_order (B1) and "every new detector off is main" (B3).

B1  The material reading cut true sentences of six kinds: «всё равно» read as equality, an engine score «больше N пешек
    перевеса» after «после …» read as material, «Плюс …» as a conjunction, a noun list «лишние слон, конь и пешка» and
    «впереди на ферзя, слона и двух коней» read to its first item only, «всё равно потеряют материал». The reader now
    reads the whole noun list, keeps evaluations and idioms out and treats «после …» as a condition; a list it cannot
    finish is left unjudged.
B3  material_order 'off' is main's material reading exactly (its 29.10 game-board fix included); book_wait, which
    nothing read, is no detector; F5's structure readings (proposals, recapture pairs, line walk) have their own switch
    (structure_read).

Boards and wordings here are new (not the reported sentences).
"""
from __future__ import annotations

import sys
from pathlib import Path

import chess
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
from ctx_fixture import run_answer  # noqa: E402

from src import answer_check as ac  # noqa: E402
from src import config  # noqa: E402
from src.material_frames import mask_idioms, read  # noqa: E402

# White up a rook, a knight and a pawn (+9): Black's h8 rook, g8 knight and h7 pawn are gone
UP9 = "rnbqkb2/ppppppp1/8/8/8/8/PPPPPPPP/RNBQKBNR w KQq - 0 1"
# White up a pawn (Black's h-pawn is gone)
UP1 = "rnbqkbnr/ppppppp1/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
# equal material, an open game
EVEN = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
# Black up a queen and a bishop (+12): White's d1 queen and f1 bishop are gone
DOWN12 = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNB1K1NR w KQkq - 0 1"


@pytest.fixture(autouse=True)
def _switches(monkeypatch):
    for k in ("COACH_DETECTORS_OFF", "COACH_DETECTORS_SHADOW"):
        monkeypatch.delenv(k, raising=False)


def _material(fen: str, sentence: str) -> list:
    ctx = ac.CheckContext.from_fens([fen])
    ctx.language = "ru"
    return [i for i in ac.check_sentence(sentence, ctx) if i.startswith("material")]


# ── B1: idioms carry no material ─────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "Чёрные всё равно отыграют материал.",
    "Белым всё равно придётся отдать материал.",
    "Чёрные все-равно потеряют материал, как ни защищайся.",
    "Плюс ко всему, у чёрных слабый король.",
    "Лишний раз проверь, что пешка e4 защищена.",
])
def test_idioms_are_no_material_claim(sentence):
    assert _material(UP1, sentence) == []


def test_mask_keeps_offsets():
    s = "белые все равно выиграют материал"
    assert len(mask_idioms(s)) == len(s) and "равно" not in mask_idioms(s)


@pytest.mark.parametrize("sentence", ["Материал сейчас равный.", "Материально позиция равная."])
def test_equality_still_judged(sentence):
    assert _material(UP1, sentence)


# ── B1: an engine score and «после …» are no material now ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "После любого другого хода у белых больше трёх пешек перевеса.",
    "Остальные ходы хуже: после них у чёрных больше двух пешек перевеса.",
    "У белых больше пяти пешек на доске.",
    "У чёрных на ладью больше после размена на e5.",
    "Белые будут впереди на ладью, если чёрные возьмут на e4.",
])
def test_conditions_and_scores_are_unjudged(sentence):
    assert _material(EVEN, sentence) == []


@pytest.mark.parametrize("sentence", [
    "У белых на две пешки больше.",
    "Белые опережают соперника на две пешки.",
    "У чёрных на ладью больше.",
])
def test_a_lead_now_is_still_judged(sentence):
    assert _material(EVEN, sentence)


def test_more_than_n_is_no_lead():
    assert [(c.kind, c.points) for c in read("У чёрных больше четырёх пешек.")] == []
    assert [(c.kind, c.points) for c in read("Чёрные больше на две пешки по материалу.")] == [("lead", 2)]


# ── B1: «плюс» with no side before it is a conjunction ─────────────────────────────────────────────────────────────
def test_plus_as_a_conjunction():
    assert _material(EVEN, "Плюс конь уходит с поля, куда белые хотели поставить слона.") == []
    assert _material(EVEN, "Минус этого плана в том, что у белых отстаёт развитие.") == []
    assert _material(EVEN, "У белых плюс две пешки.")  # a side before it: a lead, judged


# ── B1: the whole noun list ──────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "У белых лишние ладья, конь и пешка.",
    "Лишние ладья, конь и пешка — у белых.",
    "Белые впереди на ладью, коня и пешку.",
    "Белые опережают чёрных на ладью, коня и пешку.",
    "Белые впереди на ладью, коня и пешку — это решает.",
])
def test_a_true_list_is_read_whole(sentence):
    assert _material(UP9, sentence) == []


@pytest.mark.parametrize("sentence", [
    "Чёрные впереди на ферзя и слона.",
    "Чёрные опережают на ферзя и слона, это решающий перевес.",
    "У чёрных перевес в ферзя и слона.",
])
def test_a_true_list_on_another_board(sentence):
    assert _material(DOWN12, sentence) == []


@pytest.mark.parametrize("fen,sentence", [
    (UP9, "Белые впереди на ладью и пешку."),  # +6 said, +9 on the board
    (UP9, "У чёрных лишние ладья и конь."),  # the other side
    (DOWN12, "Чёрные впереди на ферзя."),  # +9 said, +12 on the board
])
def test_a_false_list_or_count_is_still_cut(fen, sentence):
    assert _material(fen, sentence)


def test_a_list_read_in_part_is_left_unjudged():
    # «, и две пешки» goes past the clause boundary: the reader cannot finish the list — no verdict either way
    assert _material(UP9, "Белые впереди на ладью, коня, и две пешки.") == []
    assert [(c.points, c.atleast) for c in read("У белых лишние слон, конь и пешка.")] == [(7, True)]
    assert [c.points for c in read("Белые впереди на ферзя, слона и двух коней.")] == [18]


def test_a_new_subject_after_an_oblique_amount_is_not_an_item():
    assert [c.points for c in read("Белые впереди на пешку и конь у них сильнее.")] == [1]


# ── B3: material_order 'off' is main's reading, its 29.10 game-board fix included ──────────────────────────────────
def _game(moves: str, student: str):
    sans = moves.split()
    b = chess.Board()
    for m in sans:
        b.push_san(m)
    color = chess.WHITE if student == "w" else chess.BLACK
    ctx = ac.CheckContext.from_fens([b.fen()], [" ".join(sans)], student_color=color)
    ctx.game_moves = sans
    first = 0 if color == chess.WHITE else 1
    ctx.game_engine_moves = [m for i, m in enumerate(sans) if i % 2 != first]
    ctx.language = "ru"
    return ctx


@pytest.mark.parametrize("mode", ["", "material_order"])
def test_the_board_now_in_a_game_whatever_the_switch(monkeypatch, mode):
    # a move ago White was a pawn up (2.exd5), now (2...Qxd5) the material is equal: main's 29.10 fix judges the board
    # now — and it stays on when material_order is off
    monkeypatch.setenv("COACH_DETECTORS_OFF", mode)
    issues = run_answer(["Так что теперь у белых на пешку больше."], _game("e4 d5 exd5 Qxd5", "b"))[-1][1]
    assert issues and "material is equal" in issues[0]


@pytest.mark.parametrize("fen,sentence", [
    (UP9, "Белые впереди на ладью и пешку."),
    (EVEN, "Белые опережают соперника на две пешки."),
    (UP1, "Материал сейчас равный."),
    (EVEN, "У чёрных на ладью больше после размена на e5."),
    (UP1, "Чёрные всё равно отыграют материал."),
])
def test_off_is_mains_reading(monkeypatch, fen, sentence):
    monkeypatch.setenv("COACH_DETECTORS_OFF", "material_order")
    ctx = ac.CheckContext.from_fens([fen])
    text = sentence.lower().replace("ё", "е")
    assert ac._material_issues(text, sentence, ctx) == ac._material_issues_v1029(text, sentence, ctx)


def test_shadow_shows_mains_and_records_the_new(monkeypatch):
    monkeypatch.setenv("COACH_DETECTORS_SHADOW", "material_order")
    ctx = ac.CheckContext.from_fens([EVEN])
    s = "Белые опережают соперника на две пешки."
    assert ac._material_issues(s.lower(), s, ctx) == []  # main does not read this word order
    assert ctx.detector_shadow and ctx.detector_shadow[0][0] == "material_order"


def test_a_broken_new_reading_falls_back_to_mains(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("broken")

    monkeypatch.setattr(ac, "_material_issues_new", boom)
    ctx = ac.CheckContext.from_fens([EVEN])
    s = "у белых на две пешки больше."
    assert ac._material_issues(s, s, ctx) == ac._material_issues_v1029(s, s, ctx) != []


# ── B3: the other switches ───────────────────────────────────────────────────────────────────────────────────────
def test_book_wait_is_no_detector():
    assert "book_wait" not in config.DETECTOR_DEFAULTS
    assert config.detector_mode("structure_read") == "on"


@pytest.mark.parametrize("sentence,san", [("Выбери Nf3.", "Nf3"), ("Играем Nf3.", "Nf3")])
def test_structure_read_switch(monkeypatch, sentence, san):
    ctx = ac.CheckContext.from_fens([chess.STARTING_FEN])
    assert ac.proposed_move(sentence, ctx)[2] == san
    monkeypatch.setenv("COACH_DETECTORS_OFF", "structure_read")
    assert ac.proposed_move(sentence, ac.CheckContext.from_fens([chess.STARTING_FEN])) is None  # main's words
    monkeypatch.delenv("COACH_DETECTORS_OFF")
    lesson = ac.CheckContext.from_fens([chess.STARTING_FEN])
    lesson.relation_surface = "lesson"
    assert ac.proposed_move(sentence, lesson) is None  # the lesson tutor keeps main's reading


def test_structure_read_shadow_records(monkeypatch):
    monkeypatch.setenv("COACH_DETECTORS_SHADOW", "structure_read")
    ctx = ac.CheckContext.from_fens([chess.STARTING_FEN])
    assert ac.proposed_move("Выбери Nf3.", ctx) is None
    assert ctx.detector_shadow and ctx.detector_shadow[0][0] == "structure_read"
    assert ac.proposed_move("Лучше Nf3.", ac.CheckContext.from_fens([chess.STARTING_FEN]))[2] == "Nf3"


def test_structure_read_switch_brings_mains_recapture_pair(monkeypatch):
    # «Nxd4 Nxd4 exd4» from 1.e4 e5 2.Nf3 Nc6 3.d4 is legal (F5 plays the run); main judged the last pair alone
    b = chess.Board()
    for m in "e4 e5 Nf3 Nc6 d4".split():
        b.push_san(m)
    s = "Обычно бывает Nxd4 Nxd4 exd4, и пешка возвращается в центр."
    assert ac._recapture_issues(s, ac.CheckContext.from_fens([b.fen()])) == []
    monkeypatch.setenv("COACH_DETECTORS_OFF", "structure_read")
    assert ac._recapture_issues(s, ac.CheckContext.from_fens([b.fen()])) == \
        ac._recapture_issues_v1031(s, ac.CheckContext.from_fens([b.fen()])) != []
