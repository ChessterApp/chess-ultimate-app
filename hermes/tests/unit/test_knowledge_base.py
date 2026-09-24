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

    programme = {"courses": [{"id": "c", "slug": "tactics-101", "title": "Tactics", "title_ru": "Тактика",
                              "modules": [{"id": "m", "title": "Forks", "title_ru": "Вилки",
                                           "lessons": [{"id": "l", "slug": "knight-fork", "title": "Knight fork",
                                                        "title_ru": "Вилка конём"}]}]}]}
    monkeypatch.setattr(lp, "fetch_programme", lambda *a, **k: programme)
    monkeypatch.setattr(lp, "fetch_progress", lambda *a, **k: {"l": {"status": "completed"}})
    out = get_topic("fork", locale="ru", user_id="u1", topics=topics)
    assert out["site_lessons"][0]["slug"] == "knight-fork"
    assert out["site_lessons"][0]["status"] == "completed"
    assert out["site_lessons"][0]["url"].endswith("/learn/tactics-101/knight-fork")


@pytest.mark.unit
def test_content_dir_ships_with_the_repo():
    assert (Path(kb.CONTENT_DIR) / "README.md").exists()
    assert len(list(Path(kb.CONTENT_DIR).glob("*.yaml"))) == 7
