"""The tactics warm-up is a mixed set at the student's level (tester's report 16.11, fixed 17.11).

The daily plan's card «Разминка: тактика» sent the generic «Дай мне тактическую задачу» — the next task of the
student's programme —, so a beginner got five near-identical rook mates of one set. The card now asks for the warm-up
in its own words, the words are read here (src/board_lock.asks_warmup) and the set is built from the puzzle database:
N puzzles of different motifs around the student's rating, none shown before, lined up in the session's queue.
"""

import csv
import json
import random
from pathlib import Path
from unittest.mock import MagicMock, patch

import chess
import pytest
from fastapi.testclient import TestClient

from src import config, puzzle_db
from src.board_lock import asks_warmup, wants_new_puzzle
from src.daily_plan import PUZZLES_PER_CARD
from src.intent import read_intent
from src.server import app, session_store
from src.tools import learning_path as lp
from src.tools import puzzles as pz
from src.user_profile import UserProfile

RU = "Разминка: дай мне 5 разных тактических задач по моему уровню."
EN = "Warm-up: give me 5 different tactical puzzles at my level."
KZ = "Жаттығу: маған деңгейіме сай 5 түрлі тактикалық есеп бер."

# Two legal Lichess rows (the position before the opponent's move, then the moves); the tags are what the tests use.
_MATE = ("r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3", "g8f6 h5f7")
_TAKE = ("rnbqkbnr/ppp2ppp/8/3pp3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3", "e4d5 d8d5")
_TAGGED = [
    ("fork01", "fork", 1180), ("fork02", "fork", 1215), ("fork03", "fork", 1240), ("pin001", "pin", 1210),
    ("skew01", "skewer", 1250), ("mate01", "mateIn1", 1190), ("hang01", "hangingPiece", 1230),
    ("sacr01", "sacrifice", 1290), ("defl01", "deflection", 1205),
    ("prom01", "promotion", 1900),       # the only promotion puzzle is far above a 1200 student
    ("fork99", "fork", 2300), ("pin099", "pin", 2310),
]
ROWS = [{"PuzzleId": pid, "FEN": (_MATE if i % 2 else _TAKE)[0], "Moves": (_MATE if i % 2 else _TAKE)[1],
         "Rating": str(rating), "RatingDeviation": "80", "Popularity": "90", "NbPlays": "5000",
         "Themes": f"{theme} short", "GameUrl": "", "OpeningTags": ""}
        for i, (pid, theme, rating) in enumerate(_TAGGED)]
THEME_OF = {pid: theme for pid, theme, _ in _TAGGED}
RATING_OF = {pid: rating for pid, _, rating in _TAGGED}


@pytest.fixture(scope="module")
def warmup_db(tmp_path_factory):
    from scripts.import_puzzles import build

    path = tmp_path_factory.mktemp("warmup") / "lichess_db_puzzle.csv"
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(ROWS[0].keys()))
        writer.writeheader()
        writer.writerows(ROWS)
    db = str(tmp_path_factory.mktemp("warmup-db") / "puzzles.db")
    assert build(str(path), db) == len(ROWS)
    return db


@pytest.fixture(autouse=True)
def _stand(monkeypatch, warmup_db):
    monkeypatch.setattr(puzzle_db, "PUZZLES_DB_PATH", warmup_db)
    monkeypatch.setattr(pz, "profile_rating", lambda user_id: 1200)
    # The programme, for the requests that are not a warm-up: one set of two rook mates.
    monkeypatch.setattr(config, "COACH_PUZZLES_FROM_SITE", True)
    monkeypatch.setattr(lp, "fetch_programme", lambda *a, **k: {"courses": [{"id": "c1", "slug": "chess-basics", "title": "Основы", "modules": [
        {"id": "m1", "title": "Ладья", "lessons": [{"id": "l1", "slug": "rook-1", "title": "Ладья — Набор 1", "module_id": "m1",
                                                    "course_id": "c1", "lesson_type": "exercise"}]}]}]})
    monkeypatch.setattr(lp, "fetch_progress", lambda *a, **k: {})
    monkeypatch.setattr(lp, "get_lesson", lambda lid, **k: {
        "lesson_id": lid, "title": "Ладья — Набор 1", "course": {"title": "Основы"},
        "url": "https://chesster.io/learn/chess-basics/rook-1",
        "puzzles": [{"n": n, "fen": "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "solution": ["Ra8#"]} for n in (1, 2, 3, 4, 5)]})


def _call(session, words, **args):
    return json.loads(pz._handle_get_puzzle(args, session_id=session.id, user_id=session.user_id, student_message=words))


# ── the words ───────────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestWords:
    @pytest.mark.parametrize("text", [
        RU, EN, KZ, "warmup: I want 3 puzzles", "Давай разминку: три задачи", "Хочу разминку — дай пару задач",
        "Give me a warm-up of three puzzles",
    ])
    def test_a_warm_up_word_a_request_and_the_puzzles(self, text):
        assert asks_warmup(text) and wants_new_puzzle(text)
        assert read_intent(text) == {"kind": "puzzle", "theme": None}

    @pytest.mark.parametrize("text", [
        "Дай мне тактическую задачу",                      # the plain request: the programme's next task, as before
        "Маған жаттығу бер",                               # «жаттығу» alone is an exercise, not a warm-up
        "Give me a tactical puzzle", "Маған тактикалық есеп бер",
        "Дай подсказку к этой задаче из разминки",         # the puzzle in front of the student
        "Покажи решение задачи из разминки",
        "Что такое разминка перед задачами?",              # nothing is asked for
        "Разминка — это полезно",
    ])
    def test_everything_else_is_not_a_warm_up(self, text):
        assert not asks_warmup(text)

    @pytest.mark.parametrize("text", [RU, EN, KZ])
    def test_the_cards_words_carry_the_number(self, text):
        assert pz.count_in_words(text) == PUZZLES_PER_CARD == 5

    @pytest.mark.parametrize("locale,text", [("ru", RU), ("en", EN), ("kz", KZ)])
    def test_the_site_sends_exactly_these_words(self, locale, text):
        messages = Path(__file__).resolve().parents[3] / "frontend" / "messages" / f"{locale}.json"
        if not messages.is_file():
            pytest.skip("the site's messages are not in this checkout")
        assert json.loads(messages.read_text(encoding="utf-8"))["coach"]["promptWarmup"] == text

    def test_a_warm_up_with_a_theme_is_puzzles_on_that_theme(self):
        assert read_intent("Разминка: дай задачи на вилку")["theme"] == "вилку"


# ── the rating ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRating:
    @pytest.mark.parametrize("stored,used", [(1450, 1450), (None, 1200), (0, 1200), (150, 600), (3300, 2800)])
    def test_the_profiles_rating_inside_the_puzzle_scale(self, monkeypatch, stored, used):
        monkeypatch.setattr(pz, "profile_rating", lambda user_id: stored)
        assert pz.student_rating("u1") == used

    def test_no_student_or_an_unreadable_profile_is_the_profiles_default(self, monkeypatch):
        def broken(user_id):
            raise RuntimeError("supabase is down")

        monkeypatch.setattr(pz, "profile_rating", broken)
        assert pz.student_rating("u1") == pz.student_rating(None) == UserProfile(user_id="x").rating == 1200

    def test_the_server_reads_it_from_the_profile_the_turn_holds(self):
        import src.server as server

        with patch("src.server.load_user_profile", return_value=UserProfile(user_id="warm-cache", rating=1630)):
            server.clear_voice_profile_cache()
            assert server._cached_profile_rating("warm-cache") == 1630
        failed = UserProfile(user_id="warm-failed")
        failed.load_failed = True
        with patch("src.server.load_user_profile", return_value=failed):
            assert server._cached_profile_rating("warm-failed") is None
        server.clear_voice_profile_cache()


# ── the set ─────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSet:
    @pytest.mark.parametrize("seed", range(8))
    def test_different_themes_near_the_rating(self, seed):
        picked = pz.warmup_puzzles(1200, 5, rng=random.Random(seed))
        ids = [p["puzzle_id"] for p in picked]
        assert len(picked) == 5 and len(set(ids)) == 5
        assert len({p["warmup_theme"] for p in picked}) == 5                      # five different motifs
        assert all(p["warmup_theme"] == THEME_OF[p["puzzle_id"]] for p in picked)
        assert all(abs(RATING_OF[i] - 1200) <= pz.WARMUP_RATING_SPREAD for i in ids)   # never prom01 (1900)
        assert all(chess.Board(p["fen"]).is_valid() and p["solution"] for p in picked)

    def test_one_motif_of_a_family_at_most_in_the_first_round(self):
        families = [set(f) for f in pz.WARMUP_FAMILIES]
        assert len(families) >= pz.MAX_COUNT                                       # ten different ones can be asked for
        assert sum(len(f) for f in families) == len(set().union(*families))        # no motif in two families
        assert all(puzzle_db.resolve_theme(t) == t for f in families for t in f)   # real Lichess tags

    def test_nothing_shown_before_comes_again(self):
        first = pz.warmup_puzzles(1200, 5, rng=random.Random(1))
        again = pz.warmup_puzzles(1200, 5, exclude_ids=[p["puzzle_id"] for p in first], rng=random.Random(1))
        assert not {p["puzzle_id"] for p in first} & {p["puzzle_id"] for p in again}

    def test_more_puzzles_than_motifs_at_this_rating_are_filled_from_the_same_motifs(self):
        picked = pz.warmup_puzzles(1200, 9, rng=random.Random(3))
        ids = {p["puzzle_id"] for p in picked}
        assert ids == {"fork01", "fork02", "fork03", "pin001", "skew01", "mate01", "hang01", "sacr01", "defl01"}
        assert [p["warmup_theme"] for p in picked[:7]].count("fork") == 1          # the different ones come first

    def test_a_rating_the_set_has_nothing_near_gives_nothing(self):
        assert pz.warmup_puzzles(1600, 5, rng=random.Random(1)) == []   # 1290 and 1900 are the nearest

    def test_without_the_database_there_is_no_set(self, monkeypatch, tmp_path):
        monkeypatch.setattr(puzzle_db, "PUZZLES_DB_PATH", str(tmp_path / "missing.db"))
        assert pz.warmup_puzzles(1200, 5) == []


# ── the request ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRequest:
    @pytest.mark.parametrize("words", [RU, EN, KZ])
    def test_the_card_gets_five_different_puzzles_one_on_the_board_four_lined_up(self, words):
        session = session_store.create("warm-" + words[:2])
        out = _call(session, words)
        assert out["warmup"] and out["source"] == "warmup" and out["rating"] == 1200 and out["count"] == 5
        assert len({p["warmup_theme"] for p in out["puzzles"]}) == 5
        assert out["board_actions"][0]["type"] == "set_puzzle" and out["on_board"] == out["puzzles"][0]["puzzle_id"]
        assert [p["puzzle_id"] for p in session.puzzle_queue] == [p["puzzle_id"] for p in out["puzzles"][1:]]
        assert {p["puzzle_id"] for p in out["puzzles"]} <= session.puzzles_shown
        assert "WARM-UP" in out["how_to_show"] and "4 are lined up" in out["how_to_show"]

    def test_dalshe_goes_through_the_set_and_nothing_repeats(self):
        session = session_store.create("warm-queue")
        first = _call(session, RU)
        seen = [first["on_board"]]
        for left in (3, 2, 1, 0):
            nxt = _call(session, "дальше")
            assert nxt["from_queue"] and nxt["left_in_queue"] == left
            seen.append(nxt["on_board"])
        assert seen == [p["puzzle_id"] for p in first["puzzles"]] and len(set(seen)) == 5
        second = _call(session, RU)   # the card again: other puzzles (four are left near this rating)
        assert second["warmup"] and not set(seen) & {p["puzzle_id"] for p in second["puzzles"]}

    def test_the_number_in_the_words_is_the_size_of_the_set_five_without_one(self):
        assert _call(session_store.create("warm-three"), "Давай разминку: три задачи")["count"] == 3
        assert _call(session_store.create("warm-default"), "Хочу разминку — дай задачи")["count"] == PUZZLES_PER_CARD

    def test_the_set_is_around_the_students_own_rating(self, monkeypatch):
        monkeypatch.setattr(pz, "profile_rating", lambda user_id: 2300)
        out = _call(session_store.create("warm-strong"), RU)
        assert out["rating"] == 2300 and {p["puzzle_id"] for p in out["puzzles"]} == {"fork99", "pin099"}

    def test_the_plain_request_is_still_the_programmes_next_task(self):
        out = _call(session_store.create("warm-plain"), "Дай мне тактическую задачу")
        assert out["source"] == "site_lesson" and out["on_board"] == "site:l1:1" and not out.get("warmup")

    def test_without_the_database_the_warm_up_falls_back_to_the_programme(self, monkeypatch, tmp_path):
        monkeypatch.setattr(puzzle_db, "PUZZLES_DB_PATH", str(tmp_path / "missing.db"))
        session = session_store.create("warm-nodb")
        out = _call(session, RU)
        assert out["source"] == "site_lesson" and out["count"] == 5 and "error" not in out
        assert len(session.puzzle_queue) == 4

    def test_a_theme_named_with_the_warm_up_is_served_as_that_theme(self):
        out = _call(session_store.create("warm-theme"), "Разминка: дай задачи на вилку", theme="вилку")
        assert not out.get("warmup")


# ── the turn ────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_the_text_turn_puts_the_warm_up_on_the_board_itself():
    client = TestClient(app)
    user = {"X-User-Id": "warm-turn"}
    sid = client.post("/api/coach/sessions", headers=user).json()["id"]
    seen = {}
    with patch("src.server._create_agent") as mock_agent, patch("src.server.load_user_profile") as mock_profile:
        mock_profile.return_value = UserProfile(user_id="warm-turn")
        agent = MagicMock()

        def _chat(message, stream_callback=None):
            seen["message"] = message
            if stream_callback:
                stream_callback("Разминка из пяти задач. Первая на доске.")
            return "ok"

        agent.chat.side_effect = _chat
        mock_agent.return_value = agent

        def turn(text):
            resp = client.post("/api/coach/chat", headers=user,
                               json={"message": text, "session_id": sid, "fen": chess.STARTING_FEN, "locale": "ru"})
            frames = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
            puzzles = [a for f in frames for a in f.get("board_actions", []) if a.get("type") == "set_puzzle"]
            cards = [f["tool_result"]["summary"] for f in frames
                     if isinstance(f.get("tool_result"), dict) and f["tool_result"].get("tool") == "get_puzzle"]
            return puzzles, cards

        first, cards = turn(RU)
        assert first and first[0]["puzzle_id"] in THEME_OF and cards[0]["queued"] == 4
        assert "WARM-UP" in seen["message"] and "4 more are lined up" in seen["message"]
        nxt, _ = turn("Дальше")
        assert nxt and nxt[0]["puzzle_id"] in THEME_OF and nxt[0]["puzzle_id"] != first[0]["puzzle_id"]
