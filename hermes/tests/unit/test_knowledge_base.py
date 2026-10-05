"""Thematic knowledge base: content integrity, lookup, and the two tools."""

import json
from pathlib import Path

import chess
import pytest

from src import knowledge_base as kb
from src.tools.knowledge_topics import get_topic, list_topics


@pytest.fixture(autouse=True)
def _fresh():
    kb.clear_cache()
    yield
    kb.clear_cache()


@pytest.fixture(scope="module")
def topics():
    return kb.load_topics(force=True)


# ── Content integrity (the YAML that ships with the coach) ────────────────


@pytest.mark.unit
def test_every_section_has_topics(topics):
    phases = {t["phase"] for t in topics.values()}
    assert phases == set(kb.PHASES), "all seven sections of the brief must be present"
    assert len(topics) >= 50


@pytest.mark.unit
def test_topics_are_complete_and_well_formed(topics):
    for slug, t in topics.items():
        assert t["title_ru"], slug
        assert len(t["summary_ru"]) >= 150, f"{slug}: summary too short"
        assert len(t["key_ideas_ru"]) >= 3, slug
        assert len(t["typical_mistakes_ru"]) >= 2, slug
        assert t["lichess_themes"], f"{slug}: needs puzzle themes for get_puzzle"
        assert 1 <= t["level"] <= 4, slug


@pytest.mark.unit
def test_every_position_is_legal_and_moves_are_sound(topics):
    count = 0
    for t in topics.values():
        for p in t["positions"]:
            count += 1
            board = chess.Board(p["fen"])
            assert board.is_valid(), (t["slug"], p["title_ru"])
            assert p["side_to_move"] in ("white", "black")
            if p["best_move"]:
                board.parse_san(p["best_move"])  # legal in the diagram
            assert p["plan_ru"], (t["slug"], p["title_ru"])
    assert count >= 45


@pytest.mark.unit
def test_puzzle_themes_are_known_to_get_puzzle(topics):
    from src.puzzle_db import resolve_theme

    for t in topics.values():
        for theme in t["lichess_themes"]:
            assert resolve_theme(theme) == theme, (t["slug"], theme)


# ── Loader behaviour ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_moves_become_fen_and_numbered_san(tmp_path):
    (tmp_path / "x.yaml").write_text(
        "- slug: t1\n  phase: opening\n  title_ru: Тест\n  summary_ru: s\n"
        "  positions:\n    - title_ru: p\n      moves: '1. e4 e5 2.Nf3 Nc6'\n      plan_ru: план\n",
        encoding="utf-8",
    )
    topics = kb.load_topics(tmp_path, force=True)
    p = topics["t1"]["positions"][0]
    assert p["fen"].startswith("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w")
    assert p["moves"] == "1.e4 e5 2.Nf3 Nc6"
    assert p["side_to_move"] == "white"


@pytest.mark.unit
def test_bad_content_is_skipped_not_fatal(tmp_path, caplog):
    (tmp_path / "x.yaml").write_text(
        "- slug: ok-topic\n  phase: tactics\n  title_ru: Норм\n  summary_ru: s\n"
        "  positions:\n"
        "    - {title_ru: good, fen: '8/8/8/4k3/8/8/8/4K2R w - - 0 1', plan_ru: p, best_move: Rh5+}\n"
        "    - {title_ru: illegal fen, fen: 'not a fen', plan_ru: p}\n"
        "    - {title_ru: illegal move, moves: '1. e4 e5 2. Kd3 Ke7', plan_ru: p}\n"
        "    - {title_ru: bad best move, fen: '8/8/8/4k3/8/8/8/4K2R w - - 0 1', plan_ru: p, best_move: Qh5}\n"
        "- slug: 'Bad Slug!'\n  phase: tactics\n  title_ru: x\n  summary_ru: s\n"
        "- slug: no-phase\n  phase: quantum\n  title_ru: x\n  summary_ru: s\n"
        "- slug: ok-topic\n  phase: tactics\n  title_ru: дубль\n  summary_ru: s\n",
        encoding="utf-8",
    )
    topics = kb.load_topics(tmp_path, force=True)
    assert list(topics) == ["ok-topic"]
    assert topics["ok-topic"]["title_ru"] == "Норм"      # first definition kept
    assert [p["title_ru"] for p in topics["ok-topic"]["positions"]] == ["good"]


@pytest.mark.unit
def test_reloads_when_a_file_changes(tmp_path):
    f = tmp_path / "x.yaml"
    f.write_text("- slug: aa\n  phase: endgame\n  title_ru: A\n  summary_ru: s\n", encoding="utf-8")
    assert list(kb.load_topics(tmp_path)) == ["aa"]
    f.write_text("- slug: bb\n  phase: endgame\n  title_ru: B\n  summary_ru: s\n", encoding="utf-8")
    import os
    os.utime(f, (f.stat().st_atime + 5, f.stat().st_mtime + 5))
    assert list(kb.load_topics(tmp_path)) == ["bb"]


# ── Lookup ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("query, expected_first", [
    ("fork", "fork"),
    ("lucena-position", "lucena-position"),
    ("D35", "minority-attack"),
    ("вилка", "fork"),
    ("что такое цугцванг", "zugzwang"),
    ("объясни тему ёж", "hedgehog"),
    ("как играть против изолированной пешки", "isolated-queens-pawn"),
    ("мат по последней горизонтали", "back-rank-mate"),
    ("Isolated queen's pawn", "isolated-queens-pawn"),
    ("minority attack", "minority-attack"),
    ("как играть против изолированной пешки", "isolated-queens-pawn"),
])
def test_find_topics(topics, query, expected_first):
    got = kb.find_topics(query, topics)
    assert got and got[0]["slug"] == expected_first, [t["slug"] for t in got]


@pytest.mark.unit
def test_find_topics_empty_and_unknown(topics):
    assert kb.find_topics("", topics) == []
    assert kb.find_topics("квантовая телепортация ладьи", topics) == []


# ── Tools ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_list_topics_shape(topics):
    out = list_topics(locale="ru", topics=topics)
    assert out["total"] == len(topics)
    assert [s["phase"] for s in out["sections"]] == list(kb.PHASES)
    assert out["sections"][0]["title"] == "Стратегия"
    en = list_topics(phase="endgame", level=1, locale="en", topics=topics)
    assert en["sections"][0]["title"] == "Endgame"
    assert all(t["level"] == 1 for t in en["sections"][0]["topics"])
    assert "error" in list_topics(phase="nope", topics=topics)
    json.dumps(out)


@pytest.mark.unit
def test_get_topic_full(topics):
    out = get_topic("lucena", locale="ru", topics=topics, with_lessons=False)
    assert out["slug"] == "lucena-position" and out["phase_title"] == "Эндшпиль"
    pos = out["positions"][0]
    assert pos["fen"] == "1K6/1P1k4/8/8/8/8/r7/2R5 w - - 0 1"
    assert pos["best_move"] == "Rc4" and pos["side_to_move"] == "white"
    assert "rookEndgame" in out["puzzle_themes"]
    assert out["key_ideas"] and out["typical_mistakes"]
    assert "site_lessons" not in out
    assert get_topic("fork", locale="en", topics=topics, with_lessons=False)["title"] == "Fork"


@pytest.mark.unit
def test_get_topic_ambiguous_and_unknown(topics):
    out = get_topic("мат", topics=topics, with_lessons=False)
    assert out.get("ambiguous") is True and len(out["topics"]) > 1
    assert "error" in get_topic("nonexistent-thing", topics=topics, with_lessons=False)


@pytest.mark.unit
def test_get_topic_lessons_fail_open(topics, monkeypatch):
    """No Supabase → the topic still comes back, just without site_lessons."""
    import src.tools.learning_path as lp

    monkeypatch.setattr(lp, "fetch_programme", lambda *a, **k: None)
    out = get_topic("fork", topics=topics)
    assert out["slug"] == "fork" and "site_lessons" not in out


@pytest.mark.unit
def test_get_topic_links_site_lessons(topics, monkeypatch):
    import src.tools.learning_path as lp

    # As on the site: no slug in the rows, English titles the address is derived from
    # (production returned «/learn/None/None» for every lesson, 2026-10-03).
    programme = {"courses": [{"id": "c", "title": "Tactics 101", "title_ru": "Тактика",
                              "modules": [{"id": "m", "title": "Forks", "title_ru": "Вилки",
                                           "lessons": [{"id": "l", "title": "Knight fork",
                                                        "title_ru": "Вилка конём"}]}]}]}
    monkeypatch.setattr(lp, "fetch_programme", lambda *a, **k: programme)
    monkeypatch.setattr(lp, "fetch_progress", lambda *a, **k: {"l": {"status": "completed"}})
    out = get_topic("fork", locale="ru", user_id="u1", topics=topics)
    first = out["site_lessons"][0]
    assert first["slug"] == "knight-fork" and first["lesson_id"] == "l"
    assert first["title"] == "Вилка конём" and first["course"] == "Тактика" and first["module"] == "Вилки"
    assert first["status"] == "completed"
    assert first["url"].endswith("/learn/tactics-101/knight-fork")


# ── The example get_topic puts on the board (2026-09-25: invented "pin") ──


@pytest.mark.unit
def test_get_topic_shows_a_verified_example_from_the_base(topics):
    out = get_topic("lucena", locale="ru", topics=topics, with_lessons=False)
    assert out["example"]["source"] == "knowledge_base"
    assert out["example"]["fen"] == "1K6/1P1k4/8/8/8/8/r7/2R5 w - - 0 1"
    assert out["board_actions"] == [
        {"type": "set_fen", "fen": "1K6/1P1k4/8/8/8/8/r7/2R5 w - - 0 1"},
        {"type": "draw_arrows", "arrows": [{"from": "c1", "to": "c4", "brush": "green"}]},  # Rc4
    ]
    assert "ALREADY on the student's board" in out["board_hint"]


@pytest.mark.unit
def test_get_topic_prefers_the_sites_own_lesson(topics, monkeypatch):
    import src.tools.learning_path as lp
    import src.tools.knowledge_topics as kt

    lesson_fen = "6k1/5ppp/8/8/8/8/5PPP/3N2K1 w - - 0 1"
    seen = {}
    monkeypatch.setattr(kt, "_related_lessons", lambda *a, **k: [
        {"lesson_id": "l-fork", "slug": "knight-fork", "title": "Вилка конём", "course": "Тактика"}])

    def _lesson(key, **kw):
        seen["key"] = key
        seen["show"] = kw.get("show")
        return {
            "lesson_id": "l-fork", "title": "Вилка конём", "course": {"slug": "tactics-101", "title": "Тактика"},
            "url": "https://chesster.io/learn/tactics-101/knight-fork",
            "exercise": {"fen": lesson_fen, "solution": ["Ne3"], "hint": "Ищите прыжок коня"},
            "puzzles": [{"n": 1, "fen": "7k/6rp/4R3/4B2K/8/8/8/8 w - - 0 1", "solution": ["Re8#"], "hint": ""}],
        }

    monkeypatch.setattr(lp, "get_lesson", _lesson)
    out = get_topic("fork", locale="ru", topics=topics)
    # Looked up by id (a title fits several lessons), without touching the board itself.
    assert seen == {"key": "l-fork", "show": False}
    ex = out["example"]
    assert ex["source"] == "site_lesson" and ex["url"].endswith("/knight-fork")
    assert ex["course"] == "Тактика" and ex["tasks"] == 2 and ex["kind"] == "exercise" and ex["solution"] == ["Ne3"]
    # A task of the site's lesson goes on as a puzzle, with no arrow giving the answer away.
    assert out["board_actions"] == [{"type": "set_puzzle", "fen": lesson_fen, "solution": ["Ne3"]}]
    hint = out["board_hint"]
    assert "the site's lesson «Вилка конём» (course «Тактика»)" in hint and "2 tasks" in hint
    assert "END the answer by inviting the student to go through the whole lesson" in hint
    assert "https://chesster.io/learn/tactics-101/knight-fork" in hint
    assert "do NOT reveal it" in hint and "Ne3" in hint


@pytest.mark.unit
def test_get_topic_teaches_from_the_lessons_own_diagram_and_text(topics, monkeypatch):
    import src.tools.learning_path as lp
    import src.tools.knowledge_topics as kt

    monkeypatch.setattr(kt, "_related_lessons", lambda *a, **k: [
        {"lesson_id": "l-fork", "slug": "knight-fork", "title": "Вилка конём", "course": "Тактика"}])
    monkeypatch.setattr(lp, "get_lesson", lambda key, **kw: {
        "lesson_id": "l-fork", "title": "Вилка конём", "course": {"slug": "tactics-101", "title": "Тактика"},
        "url": "https://chesster.io/learn/tactics-101/knight-fork",
        "lesson_text": "Двойной удар – нападение одной фигурой на две фигуры противника.",
        "diagrams": [{"fen": "6k1/8/8/3N4/8/8/8/6K1 w - - 0 1", "context": "Конь нападает на две фигуры"}],
        "puzzles": [{"n": 1, "fen": "7k/6rp/4R3/4B2K/8/8/8/8 w - - 0 1", "solution": ["Re8#"], "hint": ""}],
    })
    out = get_topic("fork", locale="ru", topics=topics)
    ex = out["example"]
    assert ex["source"] == "site_lesson" and ex["kind"] == "diagram" and ex["tasks"] == 1
    assert ex["fen"] == "6k1/8/8/3N4/8/8/8/6K1 w - - 0 1" and ex["solution"] == []
    assert ex["explanation"].startswith("Двойной удар – нападение")
    # A diagram goes on as a position to explain, not as a puzzle.
    assert out["board_actions"][0] == {"type": "set_fen", "fen": "6k1/8/8/3N4/8/8/8/6K1 w - - 0 1"}
    hint = out["board_hint"]
    assert "an explanatory diagram of the site's lesson «Вилка конём» (course «Тактика»), which has 1 tasks" in hint
    assert "«Конь нападает на две фигуры»" in hint and "teach in ITS words" in hint
    assert "END the answer by inviting the student" in hint and "/knight-fork" in hint


@pytest.mark.unit
def test_get_topic_skips_an_illegal_lesson_position(topics, monkeypatch):
    import src.tools.learning_path as lp
    import src.tools.knowledge_topics as kt

    monkeypatch.setattr(kt, "_related_lessons", lambda *a, **k: [{"slug": "broken"}])
    monkeypatch.setattr(lp, "get_lesson", lambda *a, **k: {"title": "x", "exercise": {"fen": "not a fen"}})
    out = get_topic("lucena", topics=topics)
    assert out["example"]["source"] == "knowledge_base"
    assert out["board_actions"][0]["type"] == "set_fen"
    assert "OFFER a puzzle" in out["board_hint"]


@pytest.mark.unit
def test_an_ambiguous_lesson_lookup_falls_back_to_the_base(topics, monkeypatch):
    """What production did on 2026-10-03: «Связка» matched five lessons, the
    lookup by title came back ambiguous, and the base's generic position was
    shown instead of the lesson's task."""
    import src.tools.learning_path as lp
    import src.tools.knowledge_topics as kt

    monkeypatch.setattr(kt, "_related_lessons", lambda *a, **k: [{"title": "Связка"}])
    monkeypatch.setattr(lp, "get_lesson", lambda *a, **k: {"ambiguous": True, "lessons": []})
    out = get_topic("pin", topics=topics)
    assert out["example"]["source"] == "knowledge_base"


@pytest.mark.unit
def test_get_topic_show_false_leaves_the_board_alone(topics):
    out = get_topic("lucena", topics=topics, with_lessons=False, show=False)
    assert "board_actions" not in out and "example" not in out


@pytest.mark.unit
def test_content_dir_ships_with_the_repo():
    assert (Path(kb.CONTENT_DIR) / "README.md").exists()
    assert len(list(Path(kb.CONTENT_DIR).glob("*.yaml"))) == 7


# ── arrows of a shown example ───────────────────────────────────────────────
# 2026-09-28: the voice coach showed the French advance chain with no arrow —
# 36 of 49 examples had no key move, and the voice model does not draw itself.

from src.tools.knowledge_topics import _example_actions, _example_from_base, _plan_arrows  # noqa: E402


def _arrows(actions):
    return [f"{a['from']}{a['to']}:{a['brush']}" for x in actions if x["type"] == "draw_arrows" for a in x["arrows"]]


def test_plan_arrows_take_the_first_move_of_a_line_per_piece():
    fen = "8/8/4k3/8/4K3/4P3/8/8 b - - 0 1"  # opposition, Black to move
    plan = "1...Kd6 2.Kf5 Ke7 3.Ke5 Kd7 — король занял ключевое поле."
    # Ke7 / Kd7 later in the line start from other squares — not drawn from e6.
    assert [f"{a['from']}{a['to']}" for a in _plan_arrows(fen, plan)] == ["e6d6"]


def test_plan_arrows_skip_squares_mistakes_and_follow_the_named_side():
    fen = chess.Board().fen()
    plan = ("Слон на c4 бьёт f7 — это клетки, не ходы. Ошибка 1.f3? ослабляет короля. "
            "Белые: e4, Nf3. Чёрные: ...e5, ...Nc6.")
    arrows = [f"{a['from']}{a['to']}:{a['brush']}" for a in _plan_arrows(fen, plan)]
    assert "f2f3:green" not in arrows          # «1.f3?» is the mistake
    assert not any(a.startswith("c2c4") for a in arrows)  # «на c4» is a square
    assert arrows == ["g1f3:green", "e7e5:blue", "b8c6:blue"]


def test_base_arrows_come_first_then_key_move_then_plan(tmp_path):
    fen = "rnbqkb1r/ppp2ppp/4pn2/3p2B1/2PP4/2N5/PP2PPPP/R2QKBNR b KQkq - 3 4"
    explicit = {"fen": fen, "arrows": [{"from": "g5", "to": "d8", "brush": "red"}], "key_move": "Be7",
                "note": "Чёрные развязываются ходом Be7."}
    assert _arrows(_example_actions(explicit)) == ["g5d8:red"]
    assert _arrows(_example_actions({**explicit, "arrows": []})) == ["f8e7:green"]
    assert _arrows(_example_actions({**explicit, "arrows": [], "key_move": None})) == ["f8e7:green"]


def test_arrows_field_is_parsed_and_bad_entries_dropped():
    assert kb._parse_arrows(["g5d8 red", "f8-e7", "c5d4:blue", "z9z9", "e4e4", 17]) == [
        {"from": "g5", "to": "d8", "brush": "red"},
        {"from": "f8", "to": "e7", "brush": "green"},
        {"from": "c5", "to": "d4", "brush": "blue"},
    ]


def test_most_shown_examples_come_with_arrows(topics):
    records = topics.values() if isinstance(topics, dict) else topics
    shown = [_example_actions(ex) for ex in (_example_from_base(t) for t in records) if ex]
    with_arrows = sum(1 for acts in shown if _arrows(acts))
    assert with_arrows >= 35, (with_arrows, len(shown))


@pytest.mark.unit
def test_ideas_written_as_yaml_mappings_read_as_text(topics):
    """«- Развязка: отойти с шахом…» is a mapping to YAML; the coach must get a sentence."""
    from src.knowledge_base import _as_str_list

    assert _as_str_list([{"Развязка": "отойти с шахом"}, "просто строка", {"A": ["x", "y"]}]) == [
        "Развязка: отойти с шахом", "просто строка", "A: x, y"]
    for t in (topics.values() if isinstance(topics, dict) else topics):
        for f in ("key_ideas_ru", "typical_mistakes_ru"):
            for item in t.get(f) or []:
                assert isinstance(item, str) and not item.startswith("{"), (t["slug"], item)


@pytest.mark.unit
def test_a_topic_the_base_lacks_is_taught_from_the_sites_programme(topics, monkeypatch):
    """«Мат в 3 хода» has no topic in the base but 37 sets of tasks on the site (2026-10-05):
    the sets come back as the topic, the first task on the board."""
    import src.tools.learning_path as lp

    programme = {"courses": [{"id": "c", "title": "Mate in 3", "title_ru": "Мат в 3 хода", "slug": "mate-in-3-moves",
                              "modules": [{"id": "m", "title": "Mate in 3", "title_ru": "Мат в 3 хода",
                                           "lessons": [{"id": "s1", "title": "Mate in 3 — Set 1", "title_ru": "Мат в 3 хода — Набор 1",
                                                        "slug": "mate-in-3-set-1", "lesson_type": "exercise"}]}]}]}
    monkeypatch.setattr(lp, "fetch_programme", lambda *a, **k: programme)
    monkeypatch.setattr(lp, "fetch_progress", lambda *a, **k: {})
    monkeypatch.setattr(lp, "get_lesson", lambda key, **kw: {
        "lesson_id": "s1", "title": "Мат в 3 хода — Набор 1", "course": {"slug": "mate-in-3-moves", "title": "Мат в 3 хода"},
        "url": "https://chesster.io/learn/mate-in-3-moves/mate-in-3-set-1",
        "puzzles": [{"n": 1, "fen": "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1", "solution": ["Rd8#"], "hint": ""}],
    })
    out = get_topic("мат в 3 хода", locale="ru", user_id="u1", topics=topics)
    assert "error" not in out and out["source"] == "site_programme"
    assert out["site_lessons"][0]["title"] == "Мат в 3 хода — Набор 1" and out["site_lessons"][0]["course"] == "Мат в 3 хода"
    assert out["example"]["source"] == "site_lesson" and out["example"]["kind"] == "task"
    assert out["board_actions"] == [{"type": "set_puzzle", "fen": "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1", "solution": ["Rd8#"]}]
    assert "the site's lesson «Мат в 3 хода — Набор 1» (course «Мат в 3 хода»)" in out["board_hint"]
    # nothing on the site either: the old answer, the map of the base
    monkeypatch.setattr(lp, "fetch_programme", lambda *a, **k: programme)
    out = get_topic("квантовая хромодинамика", locale="ru", user_id="u1", topics=topics)
    assert "error" in out and out["topics"]
