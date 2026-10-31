"""Package P2 of plan 31.10 (detect-1031): opening names and opening theory in the coach's answer.

  open_plain      «классический», «современный» name variations too (Classical/Orthodox/Normal/Main Line, Modern),
                  only as the variation's own name, and said of an opening only once the board is in a named variation
  open_recap      the game's own told moves and the moves a sentence denies write no line; the identity after the
                  last «:», «—», «;» is the sentence's own (st1#2)
  open_character  «спокойная игра без осложнений» said of a move the book names as a sharp line (move-najdorf; shadow)
  open_defining   advice not to make the opening's own defining move (g1-resign; shadow)

content/openings/lines.yaml is the curated data the last two read (and package P8 builds its opening ideas from).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import chess
import pytest

from src import config
from src.answer_check import CheckContext, check_sentence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
from ctx_fixture import load_ctx, run_answer  # noqa: E402

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "detect1031"
P2 = ("open_plain", "open_recap", "open_character", "open_defining")
NAME_Q = "Как называется этот дебют?"


@pytest.fixture(autouse=True)
def _book_index():
    from src.openings_book import warm_position_index

    warm_position_index()


@pytest.fixture
def all_on(monkeypatch):
    """The four P2 detectors cutting (the two shadow ones as they would after their review)."""
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW", raising=False)
    for name in P2:
        monkeypatch.setitem(config.DETECTOR_DEFAULTS, name, "on")


def _ctx(moves: str, question: str = "", game: bool = False, student=chess.WHITE) -> CheckContext:
    b = chess.Board()
    for san in moves.split():
        b.push_san(san)
    ctx = CheckContext.from_fens([b.fen()], question=question, student_color=student if game else None)
    if game:
        ctx.game_moves = moves.split()
    ctx.language = "ru"
    return ctx


def _row(rid: str):
    row = json.loads((FIX / "rows" / f"{rid}.json").read_text(encoding="utf-8"))
    ctx = load_ctx(row["ctx"])
    got = run_answer(row["prefix"] + [row["sentence"]], ctx, live_game=row["turn"].get("live_game"))
    return got[-1][1], ctx


# ── the data ────────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_lines_yaml_is_the_books():
    """Every opening's moves are legal and reach a position the book files under its name; every sharp line is a
    name the book has; every opening has at least one move of its own side."""
    from src.answer_check_openings import opening_lines
    from src.openings_book import _split_moves, get_book

    data = opening_lines()
    book = get_book()
    names = {e[1] for e in book.entries}
    assert len(data["openings"]) >= 30 and len(data["sharp"]) >= 25
    seen = set()
    for o in data["openings"]:
        assert o["book"] not in seen
        seen.add(o["book"])
        assert o["side"] in ("white", "black") and o["defining_moves"] and o["ru"] and o["idea"]
        assert o["main"].startswith(o["defining"]), o["book"]
        for key in ("defining", "main"):
            b = chess.Board()
            for san in _split_moves(o[key]):
                b.push_san(san)
            reached, _ = book.lineage(b)
            assert any(e[1] == o["book"] or e[1].startswith(o["book"] + ":") for e in reached), (o["book"], key)
    for s in data["sharp"]:
        assert s["name"] in names, s["name"]
        assert s["why"]


# ── st1#2 (must): open_plain + open_recap ───────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_st1_2_the_classical_sicilian_on_2_d6_is_cut_with_the_books_name():
    issues, _ = _row("st1_2")
    assert len(issues) == 1
    issue = issues[0]
    assert "has not reached the Sicilian Defense: Classical Variation" in issue
    assert "5. Nc3 Nc6" in issue and "Modern Variations (B50)" in issue


@pytest.mark.unit
@pytest.mark.parametrize("off", ["open_plain", "open_recap"])
def test_st1_2_needs_both_switches(monkeypatch, off):
    monkeypatch.setenv("COACH_DETECTORS_OFF", off)
    issues, _ = _row("st1_2")
    assert issues == []


@pytest.mark.unit
def test_st1_2_in_shadow_is_logged_not_cut(monkeypatch):
    monkeypatch.setenv("COACH_DETECTORS_SHADOW", "open_plain")
    issues, ctx = _row("st1_2")
    assert issues == []
    shadow = getattr(ctx, "detector_shadow", [])
    assert shadow and shadow[0][0] == "open_plain" and "Classical Variation" in shadow[0][2][0]


@pytest.mark.unit
def test_the_lesson_tutor_gets_none_of_them():
    ctx = _ctx("e4 c5 Nf3 d6", game=True)
    ctx.relation_surface = "lesson"
    assert check_sentence("Nf3 — и чёрные ответили d6: это классическая сицилианская.", ctx) == []


@pytest.mark.unit
@pytest.mark.parametrize("moves,question,game,text,wrong", [
    # the same class in other words
    ("e4 c5 Nf3 d6", "", True, "1.e4 c5 2.Nf3 d6 — это классическая сицилианская защита.", "Classical Variation"),
    ("e4 c5 Nf3 d6", "", True, "Nf3 — и чёрные ответили d6: это вариант Найдорфа.", "Najdorf Variation"),
    ("e4 c5 Nf3 d6", "", True, "Ты сыграл Nf3, чёрные ответили d6: это сицилианская защита, вариант «классический».",
     "Classical Variation"),
    ("e4 c5", NAME_Q, False, "Это современный вариант сицилианской защиты.", "Modern Variations"),
    ("e4 e5 Nf3 Nc6 Bb5", NAME_Q, False, "Это классический вариант испанской партии.", "Ruy Lopez: Classical Variation"),
])
def test_a_plain_variation_the_board_has_not_reached_is_cut(moves, question, game, text, wrong):
    issues = check_sentence(text, _ctx(moves, question, game=game))
    assert any(f"has not reached the" in i and wrong in i for i in issues), issues


@pytest.mark.unit
@pytest.mark.parametrize("moves,question,game,text", [
    # a sub-line's name is not the variation's own: «Ruy Lopez: Morphy Defense, Classical Defense Deferred»
    ("e4 e5 Nf3 Nc6 Bb5 a6", NAME_Q, False, "Это классическая испанская партия."),
    # a line the sentence writes beyond the game (not denied) — the name may be about it
    ("e4 c5 Nf3 d6", "", True, "Nf3 — и чёрные ответили d6: это классическая сицилианская, с ...g6."),
    # a line written from move 1 that is not the game's record
    ("e4 c5 Nf3 d6", "", True, "1.e4 c5 2.Nf3 Nc6 — это классическая сицилианская."),
    # the board is in the variation
    ("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 Nc6", "", True, "Nc3 — и чёрные ответили Nc6: это классическая сицилианская."),
    # a hedge, a condition
    ("e4 c5 Nf3 d6", "", True, "Nf3 — и чёрные ответили d6: это может стать классической сицилианской."),
    ("e4 c5 Nf3 d6", "", True, "Nf3 — d6: если белые сыграют d4, это будет классический вариант."),
    # «классический» of something that is not an opening
    ("e4 c5 Nf3 d6", "", True, "Nf3 — и чёрные ответили d6: это классический план за белых."),
])
def test_true_or_unjudged_plain_names_pass(all_on, moves, question, game, text):
    assert check_sentence(text, _ctx(moves, question, game=game)) == []


@pytest.mark.unit
def test_switched_off_the_check_is_mains(monkeypatch):
    """open_plain and open_recap off: the names and the lines are read as on main 02bb40d0."""
    from src import answer_check_openings as ao

    monkeypatch.setenv("COACH_DETECTORS_OFF", "open_plain,open_recap,open_character,open_defining")
    ctx = _ctx("e4 c5", "Как называется этот вариант?")
    assert ao._names_by_mode("Это открытый вариант сицилианской защиты.", ctx) == ao._name_issues(
        "Это открытый вариант сицилианской защиты.", ctx)
    assert check_sentence("Это классический вариант испанской партии.",
                          _ctx("e4 e5 Nf3 Nc6 Bb5", NAME_Q)) == []


# ── move-najdorf (stretch): open_character ──────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_move_najdorf_is_shadow_by_default_and_logged():
    issues, ctx = _row("move-najdorf")
    assert issues == []
    shadow = [s for s in getattr(ctx, "detector_shadow", []) if s[0] == "open_character"]
    assert len(shadow) == 1 and "English Attack" in shadow[0][2][0]


@pytest.mark.unit
def test_move_najdorf_on_names_the_english_attack(all_on):
    issues, _ = _row("move-najdorf")
    assert len(issues) == 1
    assert "6.Be3 is the Sicilian Defense: Najdorf Variation, English Attack (B90)" in issues[0]
    assert "sharp, tactical" in issues[0]


@pytest.mark.unit
@pytest.mark.parametrize("moves,text", [
    ("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6 Be3 Bg7 f3 O-O Qd2 Nc6", "9.Сc4 — спокойная позиционная игра без риска."),
    ("e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5", "6.Кxf7 ведёт к тихой игре."),
    ("e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 O-O c3", "8...d5 — спокойное продолжение без осложнений."),
])
def test_calm_words_on_other_sharp_lines(all_on, moves, text):
    issues = check_sentence(text, _ctx(moves, "Какие тут главные продолжения?"))
    assert any("sharp, tactical" in i for i in issues), issues


@pytest.mark.unit
def test_calm_words_on_a_quiet_line_pass(all_on):
    ctx = _ctx("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6")
    for text in ("6.Сe2 — спокойная классика.", "6.Сe2 ведёт к спокойной игре без осложнений.",
                 "Если хочешь спокойной игры, сыграй 6.Сe2."):
        assert check_sentence(text, ctx) == [], text


# ── g1-resign (stretch): open_defining ──────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_g1_resign_is_shadow_by_default_and_logged():
    issues, ctx = _row("g1-resign-opening")
    assert issues == []
    shadow = [s for s in getattr(ctx, "detector_shadow", []) if s[0] == "open_defining"]
    assert len(shadow) == 1 and "1. e4 Nf6" in shadow[0][2][0]


@pytest.mark.unit
def test_g1_resign_on_gives_the_defining_and_main_moves(all_on):
    issues, _ = _row("g1-resign-opening")
    assert len(issues) == 1
    assert "Alekhine Defense is defined by 1. e4 Nf6" in issues[0] and "2. e5 Nd5" in issues[0]


@pytest.mark.unit
@pytest.mark.parametrize("moves,text,opening", [
    ("e4 c5", "Если играешь сицилианскую, лучше не двигать пешку c сразу — сначала e6.", "Sicilian Defense"),
    ("d4 Nf6 c4 e6 Nc3", "В защите Нимцовича не стоит ставить слона на b4.", "Nimzo-Indian Defense"),
    ("e4 e5 Nf3 Nc6", "Если играешь испанскую партию, не спеши выводить слона на b5.", "Ruy Lopez"),
])
def test_other_openings_own_moves_advised_against(all_on, moves, text, opening):
    issues = check_sentence(text, _ctx(moves))
    assert any(f"the {opening} is defined by" in i for i in issues), issues


# ── the true controls with every P2 detector cutting ───────────────────────────────────────────────────────────

def _controls():
    data = json.loads((FIX / "negatives" / "P2.json").read_text(encoding="utf-8"))
    return data["controls"]


@pytest.mark.unit
@pytest.mark.parametrize("control", _controls(), ids=[c["id"] for c in _controls()])
def test_p2_controls_clean_with_everything_on(all_on, control):
    moves = control["moves"].split()
    student = {"w": chess.WHITE, "b": chess.BLACK}.get(control.get("student") or "")
    ctx = _ctx(control["moves"], control.get("question") or "", game=student is not None,
               student=student if student is not None else chess.WHITE)
    got = run_answer(list(control.get("before") or []) + [control["sentence"]], ctx)
    assert got[-1][1] == [], f"{control['id']}: {got[-1][1]} — {control['why']}"
    assert moves
