"""The warm-up is exactly the puzzles asked for: each has its place, the last one ends it (tester's report 17.11,
fixed 18.11).

«Разминка: тактика, 5 задач»: the tester solved five, then a sixth came, then a seventh; nowhere was it shown which
puzzle of the set this is, and there was no summary at the end. The set was only a queue — once it ran dry the puzzle
panel's «Дальше» (it sends the plain «Дай мне тактическую задачу») was the programme's next task again, and the
place of a puzzle was left to the model. The session now keeps the warm-up itself (src/warmup.py): the place of
every puzzle is the server's and is written by the server at the head of the answer, the request after the last
puzzle sets none and gets the ending — with the count of solved puzzles when the board showed every one of them
solved (or the system showed its solution), and without a count otherwise.
"""

import csv
import json
from unittest.mock import MagicMock, patch

import chess
import pytest
from fastapi.testclient import TestClient

from src import config, puzzle_db, warmup
from src.board_lock import asks_warmup, wants_new_puzzle
from src.intent import read_intent
from src.server import app, session_store
from src.tool_summaries import build_summary
from src.tools import learning_path as lp
from src.tools import puzzles as pz
from src.user_profile import UserProfile

RU = "Разминка: дай мне 5 разных тактических задач по моему уровню."
EN = "Warm-up: give me 5 different tactical puzzles at my level."
KZ = "Жаттығу: маған деңгейіме сай 5 түрлі тактикалық есеп бер."
PLAIN = "Дай мне тактическую задачу"   # what the puzzle panel's «Дальше» sends (coach.promptPuzzle)

# Twelve different back-rank mates (the position before the knight's move, then the moves — a Lichess row): every
# puzzle has its own start and its own final position, as real ones do.
_TAGGED = [
    ("fork01", "fork", 1180), ("pin001", "pin", 1210), ("skew01", "skewer", 1250), ("mate01", "mateIn1", 1190),
    ("hang01", "hangingPiece", 1230), ("sacr01", "sacrifice", 1290), ("defl01", "deflection", 1205),
    ("fork02", "fork", 1215), ("pin002", "pin", 1220), ("mate02", "mateIn1", 1195), ("prom01", "promotion", 1260),
    ("intr01", "intermezzo", 1240),
]
_KNIGHTS = (("h5", "f4", "bcde"), ("h6", "g4", "bcde"), ("a6", "b4", "acde"))


def _row(i, pid, theme, rating):
    frm, to, rooks = _KNIGHTS[i // 4]
    rook = rooks[i % 4]
    board = chess.Board(None)
    for square, piece in (("g1", "K"), ("f2", "P"), ("g2", "P"), ("h2", "P"), (rook + "1", "R"),
                          ("g8", "k"), ("f7", "p"), ("g7", "p"), ("h7", "p"), (frm, "n")):
        board.set_piece_at(chess.parse_square(square), chess.Piece.from_symbol(piece))
    board.turn = chess.BLACK
    line = board.copy()
    line.push_uci(f"{frm}{to}")
    line.push_uci(f"{rook}1{rook}8")
    assert line.is_checkmate()
    return {"PuzzleId": pid, "FEN": board.fen(), "Moves": f"{frm}{to} {rook}1{rook}8", "Rating": str(rating),
            "RatingDeviation": "80", "Popularity": "90", "NbPlays": "5000", "Themes": f"{theme} short",
            "GameUrl": "", "OpeningTags": ""}


ROWS = [_row(i, *tagged) for i, tagged in enumerate(_TAGGED)]


@pytest.fixture(scope="module")
def warmup_db(tmp_path_factory):
    from scripts.import_puzzles import build

    path = tmp_path_factory.mktemp("warmup-end") / "lichess_db_puzzle.csv"
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(ROWS[0].keys()))
        writer.writeheader()
        writer.writerows(ROWS)
    db = str(tmp_path_factory.mktemp("warmup-end-db") / "puzzles.db")
    assert build(str(path), db) == len(ROWS)
    return db


@pytest.fixture(autouse=True)
def _stand(monkeypatch, warmup_db):
    monkeypatch.setattr(puzzle_db, "PUZZLES_DB_PATH", warmup_db)
    monkeypatch.setattr(pz, "profile_rating", lambda user_id: 1200)
    monkeypatch.setattr(config, "COACH_TWO_STAGE", False)
    # The programme, for the requests that are not a warm-up: one set of rook mates.
    monkeypatch.setattr(config, "COACH_PUZZLES_FROM_SITE", True)
    monkeypatch.setattr(lp, "fetch_programme", lambda *a, **k: {"courses": [{"id": "c1", "slug": "chess-basics", "title": "Основы", "modules": [
        {"id": "m1", "title": "Ладья", "lessons": [{"id": "l1", "slug": "rook-1", "title": "Ладья — Набор 1", "module_id": "m1",
                                                    "course_id": "c1", "lesson_type": "exercise"}]}]}]})
    monkeypatch.setattr(lp, "fetch_progress", lambda *a, **k: {})
    monkeypatch.setattr(lp, "get_lesson", lambda lid, **k: {
        "lesson_id": lid, "title": "Ладья — Набор 1", "course": {"title": "Основы"},
        "url": "https://chesster.io/learn/chess-basics/rook-1",
        "puzzles": [{"n": n, "fen": "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "solution": ["Ra8#"]} for n in (1, 2, 3, 4, 5)]})


def _ask(session, words, caller=None, **args):
    """One request of the student: their message first, as in a turn, then the puzzle step's call."""
    session.add_message("user", words)
    extra = {"caller": caller} if caller else {}
    return json.loads(pz._handle_get_puzzle(args, session_id=session.id, user_id=session.user_id,
                                            student_message=words, **extra))


def _put_up(session, result):
    """What every caller does with a result: its puzzle goes on the session's board."""
    session.ensure_board()
    session.apply_board_actions(result["board_actions"])


def _final_fen(puzzle):
    board = chess.Board(puzzle["fen"])
    for san in puzzle["solution"]:
        board.push_san(san)
    return board.fen()


def _solve(session, result):
    """The student plays the solution on the board: the page reports the position it ends in."""
    _put_up(session, result)
    session.set_board_state(_final_fen(result["puzzles"][0]))


def _through(session, first, solve=lambda n: True, words="дальше"):
    """Go through the whole set after its *first* result; the results, in order."""
    results = [first]
    for n in range(1, first["count"] + 1):
        (_solve if solve(n) else _put_up)(session, results[-1])
        if n < first["count"]:
            results.append(_ask(session, words))
    return results


# ── the place ───────────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestPlace:
    def test_every_puzzle_of_the_set_comes_with_its_place(self):
        """«Nowhere is it shown which puzzle of the set this is»: the server says it with every one of them."""
        session = session_store.create("end-place")
        results = _through(session, _ask(session, RU))
        assert [r["place"] for r in results] == [{"n": n, "of": 5} for n in (1, 2, 3, 4, 5)]
        assert all("never count the puzzles yourself" in r["how_to_show"] for r in results)
        assert "puzzle 3 of 5 of the warm-up" in results[2]["how_to_show"]

    def test_the_board_command_of_each_puzzle_carries_its_place(self):
        """18.11: the app hides the coach's words while a puzzle is on — «номер задачи нигде не видно». The set_puzzle
        command itself carries the place, for the puzzle panel; outside a warm-up the command has none."""
        session = session_store.create("end-cmd-place")
        results = _through(session, _ask(session, RU))
        assert [r["board_actions"][0]["place"] for r in results] == [{"n": n, "of": 5} for n in range(1, 6)]
        assert all(r["board_actions"][0]["type"] == "set_puzzle" for r in results)
        plain = _ask(session_store.create("end-cmd-none"), "Дай мне задачу на вилку")
        assert all("place" not in a for a in plain.get("board_actions") or [])

    def test_the_last_one_is_told_to_be_the_last(self):
        """The model must not promise a sixth: the fifth result says «дальше» will end the warm-up."""
        session = session_store.create("end-last")
        results = _through(session, _ask(session, RU))
        assert "LAST puzzle of the warm-up" in results[-1]["how_to_show"]
        assert all("LAST puzzle" not in r["how_to_show"] for r in results[:-1])

    @pytest.mark.parametrize("words,size", [("Давай разминку: три задачи", 3), ("Хочу разминку — дай задачи", 5),
                                            ("Разминка: дай 50 задач", 10)])
    def test_the_number_in_the_request_is_the_size_of_the_set(self, words, size):
        """The number the words name, five without one, ten at most (the tool's own limit)."""
        out = _ask(session_store.create("end-size-" + str(size)), words)
        assert out["count"] == size and out["place"] == {"n": 1, "of": size}

    def test_the_place_is_written_in_the_students_language(self):
        """The server's line, not the model's: Russian, English, Kazakh; a set of one has none."""
        place = {"n": 2, "of": 5}
        assert warmup.place_line(place, "ru") == "Задача 2 из 5."
        assert warmup.place_line(place, "en") == "Puzzle 2 of 5."
        assert warmup.place_line(place, "kk") == warmup.place_line(place, "kz") == "2-есеп, барлығы 5."
        assert warmup.place_line(None, "ru") == "" and warmup.lead_line({"puzzles": [{}]}, "ru") == ""
        assert warmup.lead_line({"place": place}, "ru") == "Задача 2 из 5."

    def test_a_model_reading_the_result_itself_is_told_to_say_the_place_first(self):
        """The voice coach has no server line: its result names the exact words to say, in the three languages."""
        out = _ask(session_store.create("end-say"), EN)
        assert "«Задача 1 из 5.»" in out["say_place"] and '"Puzzle 1 of 5."' in out["say_place"]
        assert "«1-есеп, барлығы 5.»" in out["say_place"]

    def test_the_card_of_a_queued_puzzle_carries_its_place_and_what_is_left(self):
        """The puzzle card's summary: «ещё 3 в очереди» under the second puzzle too, and its place for a client."""
        session = session_store.create("end-card")
        second = _through(session, _ask(session, RU))[1]
        card = build_summary("get_puzzle", {}, second)
        assert card["queued"] == 3 and card["place"] == {"n": 2, "of": 5}

    def test_a_set_of_one_is_a_puzzle_not_a_set(self, monkeypatch):
        """Nothing near the rating but one puzzle: no «1 из 1», no ending — the next request goes on as any."""
        monkeypatch.setattr(pz, "warmup_puzzles", lambda *a, **k: [dict(pz.find_puzzles(theme="fork", count=1)[0],
                                                                        warmup_theme="fork")])
        session = session_store.create("end-one")
        out = _ask(session, RU)
        assert out["count"] == 1 and "place" not in out and session.warmup is None
        assert _ask(session, "дальше").get("source") == "site_lesson"


# ── the ending ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestEnding:
    def test_the_request_after_the_last_puzzle_sets_no_sixth(self):
        """«Solved five, then a sixth came»: after the fifth «дальше» is the ending — no puzzle, nothing new shown."""
        session = session_store.create("end-sixth")
        _through(session, _ask(session, RU))
        shown = set(session.puzzles_shown)
        over = _ask(session, "дальше")
        assert over["warmup_over"] and over["count"] == 5 and over["puzzles"] == []
        # No puzzle goes up — only the board's own position again, which ends the puzzle mode (18.11, the app).
        assert [a["type"] for a in over["board_actions"]] == ["set_fen"]
        assert "NO new puzzle" in over["note"] and session.puzzles_shown == shown

    def test_the_puzzle_panels_button_ends_it_too_and_then_gives_the_programme(self):
        """The panel's «Дальше» sends the plain request: after the fifth it is the ending, and the same button once
        more is what it always was — the programme's next task (the ending says so)."""
        session = session_store.create("end-panel")
        results = _through(session, _ask(session, RU), words=PLAIN)
        assert [r["place"]["n"] for r in results] == [1, 2, 3, 4, 5]
        over = _ask(session, PLAIN)
        assert over["warmup_over"] and "programme's next task" in over["note"]
        after = _ask(session, PLAIN)
        assert after["source"] == "site_lesson" and after["on_board"] == "site:l1:1" and session.warmup is None

    def test_puzzles_solved_on_the_board_are_counted(self):
        """The page reports the board after every move: the final position of a puzzle's solution is «solved»."""
        session = session_store.create("end-solved")
        _through(session, _ask(session, RU))
        over = _ask(session, "дальше")
        assert over["solved"] == 5 and over["solution_shown"] == 0 and "5 of 5 solved" in over["note"]
        assert warmup.over_line(over, "ru") == "Разминка окончена: решено 5 из 5."
        assert warmup.over_line(over, "en") == "The warm-up is over: 5 of 5 solved."
        assert warmup.over_line(over, "kk") == "Жаттығу аяқталды: 5 есептің ішінен 5 есеп шешілді."

    def test_a_puzzle_whose_solution_the_system_showed_is_not_a_solved_one(self):
        """«Сдаюсь, покажи решение» on the third, then the shown moves played on the board: four solved of five."""
        session = session_store.create("end-shown")
        first = _ask(session, RU)
        results = [first]
        for n in range(1, 6):
            if n == 3:
                _put_up(session, results[-1])
                gave_up = "Сдаюсь, покажи решение"
                session.add_message("user", gave_up)
                shown = json.loads(pz._handle_puzzle_solution({}, session_id=session.id, student_message=gave_up))
                assert shown["ok"] and shown.get("board_actions")
                session.set_board_state(_final_fen(results[-1]["puzzles"][0]))   # they play what was shown
            else:
                _solve(session, results[-1])
            if n < 5:
                results.append(_ask(session, "дальше"))
        over = _ask(session, "дальше")
        assert over["solved"] == 4 and over["solution_shown"] == 1
        assert "the solution of the other 1 was shown" in over["note"]
        assert warmup.over_line(over, "ru") == "Разминка окончена: решено 4 из 5."

    def test_an_answer_the_board_never_showed_leaves_the_count_unsaid(self):
        """A puzzle skipped — or answered in words, which the server cannot tell from a skip: no count is said,
        only that the warm-up of five is over (never a number the server did not count)."""
        session = session_store.create("end-unknown")
        _through(session, _ask(session, RU), solve=lambda n: n != 2)
        over = _ask(session, "дальше")
        assert over["solved"] is None and over["solved_on_board"] == 4 and "do NOT say how many" in over["note"]
        assert warmup.over_line(over, "ru") == "Разминка из 5 задач окончена."
        assert warmup.over_line(over, "en") == "The warm-up of 5 puzzles is over."
        assert warmup.over_line(over, "kk") == "5 есептен тұратын жаттығу аяқталды."

    def test_the_ending_offers_only_what_exists(self):
        """What the site's flow has next, in words: the programme's puzzles, another warm-up, a game, a review."""
        session = session_store.create("end-offer")
        _through(session, _ask(session, RU))
        note = _ask(session, "дальше")["note"]
        for offered in ("puzzles of their own programme", "another warm-up", "a game", "a review"):
            assert offered in note
        assert "do not call get_puzzle or board_control" in note

    def test_dalshe_after_the_last_puzzle_is_read_as_a_puzzle_request(self):
        """The queue is empty by then: «дальше» is still about the puzzles while the warm-up waits for its ending."""
        session = session_store.create("end-intent")
        assert not session.next_puzzle_due
        results = _through(session, _ask(session, RU))
        assert results[-1]["left_in_queue"] == 0 and not session.puzzle_queue and session.next_puzzle_due
        assert read_intent("дальше", puzzle_queue=session.next_puzzle_due) == {"kind": "puzzle", "theme": None}
        _ask(session, "дальше")
        assert not session.next_puzzle_due                      # said once: «дальше» is free again

    def test_the_models_own_call_for_the_same_words_gets_the_same_answer(self):
        """The turn's step answers the words; the model calling get_puzzle for them in the same turn used to get
        the NEXT puzzle. In a warm-up it gets the same one — and after the ending the ending, never a sixth."""
        session = session_store.create("end-again")
        first = _ask(session, RU, caller="turn")
        again = json.loads(pz._handle_get_puzzle({}, session_id=session.id, student_message=RU))
        assert again["on_board"] == first["on_board"] and again["place"] == {"n": 1, "of": 5}
        assert len(session.puzzle_queue) == 4
        results = [first]
        for n in range(1, 6):
            _solve(session, results[-1])
            if n < 5:
                results.append(_ask(session, "дальше", caller="turn"))
        over = _ask(session, "дальше", caller="turn")
        again = json.loads(pz._handle_get_puzzle({}, session_id=session.id, student_message="дальше"))
        assert over["warmup_over"] and again == over

    def test_two_requests_of_the_student_in_the_same_words_are_two_requests(self):
        """The panel's button pressed again is the next puzzle, not the same one: only the model's call repeats."""
        session = session_store.create("end-twice")
        first = _ask(session, RU, caller="turn")
        second = _ask(session, PLAIN, caller="turn")
        third = _ask(session, PLAIN, caller="turn")
        assert len({first["on_board"], second["on_board"], third["on_board"]}) == 3
        assert third["place"] == {"n": 3, "of": 5}


# ── what is and is not a warm-up ────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestFrame:
    def test_a_new_warm_up_request_starts_a_new_set(self):
        """The card tapped again in the middle of a set: a new set from its first puzzle, none of the old ones."""
        session = session_store.create("end-new")
        first = _ask(session, RU)
        _solve(session, first)
        second = _ask(session, RU)
        assert second["place"] == {"n": 1, "of": 5}
        assert not {p["puzzle_id"] for p in first["puzzles"]} & {p["puzzle_id"] for p in second["puzzles"]}
        assert _ask(session, "дальше")["place"] == {"n": 2, "of": 5}

    @pytest.mark.parametrize("text", ["Ещё разминку", "Давай ещё одну разминку", "Хочу новую разминку",
                                      "Give me another warm-up", "one more warm-up", "Разминку ещё раз"])
    def test_one_more_warm_up_is_a_warm_up(self, text):
        """The ending offers «ещё разминку»: the answer to the offer is read as the request it is."""
        assert asks_warmup(text) and wants_new_puzzle(text)
        assert read_intent(text) == {"kind": "puzzle", "theme": None}

    @pytest.mark.parametrize("text", ["Разминка — это полезно, дай ещё совет", "Тағы бір жаттығу бер",
                                      "Маған жаңа жаттығу бер", "Дай подсказку к этой задаче из новой разминки"])
    def test_one_more_of_something_else_is_not(self, text):
        """«Жаттығу» is an exercise in Kazakh: «one more exercise» stays the plain request, as on 17.11."""
        assert not asks_warmup(text)

    def test_one_more_warm_up_after_the_ending_is_a_new_set_of_five(self):
        session = session_store.create("end-more")
        first = _ask(session, RU)
        _through(session, first)
        assert _ask(session, "дальше")["warmup_over"]
        more = _ask(session, "Ещё разминку")
        assert more["warmup"] and more["place"] == {"n": 1, "of": 5}
        assert not {p["puzzle_id"] for p in first["puzzles"]} & {p["puzzle_id"] for p in more["puzzles"]}

    def test_a_puzzle_asked_for_by_theme_leaves_the_warm_up(self):
        """«Дай задачу на вилку» in the middle of the set: that puzzle, no place — and the warm-up is not resumed."""
        session = session_store.create("end-theme")
        _solve(session, _ask(session, RU))
        fork = _ask(session, "Дай задачу на вилку", theme="вилку")
        assert "place" not in fork and not fork.get("warmup_over") and session.warmup is None
        assert not session.next_puzzle_due

    def test_outside_a_warm_up_dalshe_is_what_it_was(self):
        """«Дай три задачи» → «дальше»: the next of them with no place; once they are out, «дальше» is no puzzle
        request and the plain request is the programme's next task."""
        session = session_store.create("end-outside")
        three = _ask(session, "Дай три задачи")
        assert three["count"] == 3 and "place" not in three and session.warmup is None
        for left in (1, 0):
            nxt = _ask(session, "дальше")
            assert nxt["from_queue"] and nxt["left_in_queue"] == left and "place" not in nxt
        assert not session.next_puzzle_due
        assert read_intent("дальше", puzzle_queue=session.next_puzzle_due) == {"kind": "none"}
        assert not _ask(session, PLAIN).get("warmup_over")

    def test_a_warm_up_the_student_has_left_is_not_ended_later(self):
        """The fifth puzzle long gone from the board and many messages ago: «дай задачу» then is a puzzle request,
        not the ending of a warm-up nobody remembers."""
        session = session_store.create("end-left")
        _through(session, _ask(session, RU))
        session.set_board_state("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3")
        for _ in range(warmup.END_TURNS + 1):
            session.add_message("user", "А как играть в дебюте?")
        assert not session.next_puzzle_due and session.warmup is None
        assert _ask(session, PLAIN)["source"] == "site_lesson"

    def test_the_ending_is_still_due_while_the_last_puzzle_is_on_the_board(self):
        """Any number of questions about the fifth puzzle, the board still on it: «дальше» ends the warm-up."""
        session = session_store.create("end-still")
        _through(session, _ask(session, RU))
        for _ in range(warmup.END_TURNS + 3):
            session.add_message("user", "Почему именно этот ход?")
        assert session.next_puzzle_due and _ask(session, "дальше")["warmup_over"]

    def test_a_puzzle_of_the_set_put_up_by_the_model_keeps_the_count(self):
        """The model puts the next puzzle up itself (board_control set_puzzle with its id): the warm-up is at that
        puzzle, the queue does not serve it a second time."""
        session = session_store.create("end-model")
        first = _ask(session, RU)
        _solve(session, first)
        second = first["puzzles"][1]
        session.apply_board_actions([{"type": "set_puzzle", "fen": second["fen"], "solution": second["solution"],
                                      "puzzle_id": second["puzzle_id"]}])
        assert [p["puzzle_id"] for p in session.puzzle_queue] == [p["puzzle_id"] for p in first["puzzles"][2:]]
        nxt = _ask(session, "дальше")
        assert nxt["on_board"] == first["puzzles"][2]["puzzle_id"] and nxt["place"] == {"n": 3, "of": 5}

    def test_the_programmes_tasks_served_as_a_warm_up_are_framed_too(self, monkeypatch, tmp_path):
        """No puzzle database: the five tasks come from the programme — still five, each with its place, then the
        ending."""
        monkeypatch.setattr(puzzle_db, "PUZZLES_DB_PATH", str(tmp_path / "missing.db"))
        session = session_store.create("end-nodb")
        first = _ask(session, RU)
        assert first["source"] == "site_lesson" and first["warmup"] and first["place"] == {"n": 1, "of": 5}
        results = _through(session, first)
        assert [r["place"]["n"] for r in results] == [1, 2, 3, 4, 5]
        assert _ask(session, PLAIN)["warmup_over"]


# ── the turn ────────────────────────────────────────────────────────────────────────────────────

class _Turns:
    """Text turns of one session with the model replaced; every turn gives its frames, text and the model's input."""

    def __init__(self, user, locale="ru", said="Белые начинают. Ищи слабую последнюю горизонталь."):
        self.client, self.user, self.locale, self.said = TestClient(app), {"X-User-Id": user}, locale, said
        self.sid = self.client.post("/api/coach/sessions", headers=self.user).json()["id"]
        self.message = None

    def turn(self, text, fen=chess.STARTING_FEN):
        with patch("src.server._create_agent") as mock_agent, patch("src.server.load_user_profile") as mock_profile:
            mock_profile.return_value = UserProfile(user_id=self.user["X-User-Id"])
            agent = MagicMock()

            def _chat(message, stream_callback=None):
                self.message = message
                if stream_callback:
                    stream_callback(self.said)
                return self.said

            agent.chat.side_effect = _chat
            mock_agent.return_value = agent
            resp = self.client.post("/api/coach/chat", headers=self.user, json={
                "message": text, "session_id": self.sid, "fen": fen, "locale": self.locale})
        frames = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
        return {
            "text": "".join(f["delta"] for f in frames if "delta" in f),
            "puzzles": [a for f in frames for a in f.get("board_actions", []) if a.get("type") == "set_puzzle"],
            "cards": [f["tool_result"]["summary"] for f in frames
                      if isinstance(f.get("tool_result"), dict) and f["tool_result"].get("tool") == "get_puzzle"],
        }

    def stored(self):
        messages = self.client.get(f"/api/coach/sessions/{self.sid}/messages", headers=self.user).json()["messages"]
        return [m["content"] for m in messages if m["role"] == "assistant"][-1]


def _solved_fen(shown):
    return _final_fen({"fen": shown["fen"], "solution": shown["solution"]})


@pytest.mark.unit
class TestTurn:
    def test_the_answer_opens_with_the_place_written_by_the_server(self):
        """«Задача 1 из 5.» is the first line of the answer whatever the model writes; the model is told it is there
        and goes on from it; the stored message has both."""
        t = _Turns("end-turn-place")
        first = t.turn(RU)
        assert first["text"].startswith("Задача 1 из 5.\n\n") and first["text"].endswith(t.said)
        assert first["text"].count("Задача 1 из 5.") == 1 and t.stored() == first["text"]
        assert "ALREADY written the first line" in t.message and "«1 of 5»" in t.message
        assert first["cards"][0]["place"] == {"n": 1, "of": 5} and first["cards"][0]["queued"] == 4
        second = t.turn(PLAIN, fen=_solved_fen(first["puzzles"][0]))
        assert second["text"].startswith("Задача 2 из 5.\n\n") and second["puzzles"]
        assert second["cards"][0]["place"] == {"n": 2, "of": 5} and second["cards"][0]["queued"] == 3

    @pytest.mark.parametrize("locale,words,line", [("en", EN, "Puzzle 1 of 5."), ("kz", KZ, "1-есеп, барлығы 5.")])
    def test_the_place_follows_the_language_of_the_turn(self, locale, words, line):
        t = _Turns("end-turn-" + locale, locale=locale, said="White to move.")
        assert t.turn(words)["text"].startswith(line + "\n\n")

    def test_five_solved_then_the_button_again_the_ending_and_no_sixth_puzzle(self):
        """The tester's run as it should go: five puzzles solved on the board through the panel's «Дальше», the
        sixth press sets nothing and the answer opens with the server's count."""
        t = _Turns("end-turn-over", said="Отличная работа! Можно продолжить задачами программы.")
        shown = t.turn(RU)["puzzles"][0]
        for n in (2, 3, 4, 5):
            step = t.turn(PLAIN, fen=_solved_fen(shown))
            assert step["text"].startswith(f"Задача {n} из 5.\n\n")
            shown = step["puzzles"][0]
        over = t.turn(PLAIN, fen=_solved_fen(shown))
        assert over["puzzles"] == [] and over["cards"] == []
        assert over["text"] == "Разминка окончена: решено 5 из 5.\n\n" + t.said and t.stored() == over["text"]
        assert "The warm-up is OVER" in t.message and "5 of 5 solved" in t.message
        assert "Do not write that line again" in t.message
        after = t.turn(PLAIN, fen=_solved_fen(shown))             # the button once more: the programme, as always
        assert after["puzzles"] and "Задача" not in after["text"].split("\n")[0]

    def test_typed_dalshe_after_the_last_puzzle_is_the_ending_without_a_count(self):
        """«Дальше» typed with the fifth puzzle unsolved on the board: the ending, and no number the server did not
        count."""
        t = _Turns("end-turn-typed", said="Хорошо поработали.")
        shown = t.turn(RU)["puzzles"][0]
        for _ in range(4):
            shown = t.turn("Дальше", fen=_solved_fen(shown))["puzzles"][0]
        over = t.turn("Дальше", fen=shown["fen"])
        assert over["puzzles"] == [] and over["text"].startswith("Разминка из 5 задач окончена.\n\n")
        assert "do NOT say how many were solved" in t.message


# ── the voice paths ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestVoice:
    def _tool(self, client, user, sid, words):
        return client.post("/api/coach/tool/get_puzzle", headers=user, json={
            "args": {"count": 1}, "session_id": sid, "utterance": words, "caller": "site"}).json()

    def test_the_voice_pages_call_gets_the_place_and_the_ending(self):
        """The voice page asks get_puzzle for the student's words (POST /api/coach/tool/get_puzzle): the same set,
        the same places, and after the fifth no puzzle but the ending — the result the coach words aloud."""
        client, user = TestClient(app), {"X-User-Id": "end-voice"}
        sid = client.post("/api/coach/sessions", headers=user).json()["id"]
        first = self._tool(client, user, sid, RU)
        assert first["result"]["place"] == {"n": 1, "of": 5} and first["board_actions"][0]["type"] == "set_puzzle"
        seen = [first["result"]["on_board"]]
        for n in (2, 3, 4, 5):
            nxt = self._tool(client, user, sid, "дальше")
            assert nxt["result"]["place"] == {"n": n, "of": 5} and "say_place" in nxt["result"]
            seen.append(nxt["result"]["on_board"])
        assert len(set(seen)) == 5
        intent = client.post("/api/coach/voice/intent", headers=user, json={"text": "дальше", "session_id": sid}).json()
        assert intent == {"kind": "puzzle", "theme": None}        # «дальше» is still about the puzzles
        over = self._tool(client, user, sid, "дальше")
        assert over["result"]["warmup_over"] and [a["type"] for a in over["board_actions"]] == ["set_fen"]
        assert over["result"]["solved"] is None                   # answered aloud: the server saw no board

    def test_the_voice_model_putting_the_next_puzzle_up_itself_keeps_the_count(self):
        """The voice page's note lets the model put the lined-up puzzles up with board_control set_puzzle: the
        warm-up follows the board — «дальше» then is the third puzzle, not the second once more."""
        client, user = TestClient(app), {"X-User-Id": "end-voice-model"}
        sid = client.post("/api/coach/sessions", headers=user).json()["id"]
        first = self._tool(client, user, sid, RU)["result"]
        second, third = first["puzzles"][1], first["puzzles"][2]
        put = client.post("/api/coach/tool/board_control", headers=user, json={
            "args": {"action_type": "set_puzzle", "puzzle_id": second["puzzle_id"]}, "session_id": sid,
            "utterance": "решил, давай следующую"}).json()
        assert put["board_actions"][0]["puzzle_id"] == second["puzzle_id"]
        nxt = self._tool(client, user, sid, "дальше")["result"]
        assert nxt["on_board"] == third["puzzle_id"] and nxt["place"] == {"n": 3, "of": 5}

    def test_the_voice_pipeline_is_the_text_turn(self):
        """«?voice=pipeline» sends the heard words through /api/coach/chat (speech): the same first line is read."""
        client, user = TestClient(app), {"X-User-Id": "end-pipeline"}
        sid = client.post("/api/coach/sessions", headers=user).json()["id"]
        with patch("src.server._create_agent") as mock_agent, patch("src.server.load_user_profile") as mock_profile:
            mock_profile.return_value = UserProfile(user_id="end-pipeline")
            agent = MagicMock()
            agent.chat.side_effect = lambda message, stream_callback=None: (stream_callback("Белые начинают."), "ok")[1]
            mock_agent.return_value = agent
            resp = client.post("/api/coach/chat", headers=user, json={
                "message": RU, "session_id": sid, "fen": chess.STARTING_FEN, "locale": "ru", "speech": True})
        text = "".join(json.loads(line[6:]).get("delta", "") for line in resp.text.splitlines()
                       if line.startswith("data: "))
        assert text.startswith("Задача 1 из 5.")


@pytest.mark.unit
class TestPaused:
    """A game pasted in the middle of a warm-up: the answer opens with «Разминка прервана на задаче 1 из 5.», once —
    it ended without a word before (open since 20.11, src/warmup.paused)."""

    PASTED = "Разбери мою партию: 1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7"

    def test_a_pasted_game_pauses_it_said_once(self):
        t = _Turns("end-turn-paused")
        first = t.turn(RU)
        shown = first["puzzles"][0]
        pasted = t.turn(self.PASTED, fen="r1bqk2r/1pppbppp/p1n2n2/4p3/B3P3/5N2/PPPP1PPP/RNBQ1RK1 w kq - 4 6")
        # The break is the answer's LAST line, the server's (26.11: it was the first — over an answer about a game).
        assert not pasted["text"].startswith("Разминка")
        assert pasted["text"].endswith("Разминка приостановлена на задаче 1 из 5 — напиши «дальше», чтобы вернуться к ней.")
        assert "[Warm-up paused]" in t.message and "adds its own closing line" in t.message
        again = t.turn("А какой план у белых?", fen="r1bqk2r/1pppbppp/p1n2n2/4p3/B3P3/5N2/PPPP1PPP/RNBQ1RK1 w kq - 4 6")
        assert "Разминка" not in again["text"]
        # The student is back on the puzzle's own board and says «дальше»: theirs to skip — the next one.
        back = t.turn("дальше", fen=shown["fen"])
        assert back["text"].startswith("Задача 2 из 5.")

    def test_дальше_brings_back_the_puzzle_left_unsolved(self):
        """«…напиши «дальше», чтобы вернуться к ней» — and the fourth came, the third left unsolved (tester 26.11)."""
        game = "r1bqk2r/1pppbppp/p1n2n2/4p3/B3P3/5N2/PPPP1PPP/RNBQ1RK1 w kq - 4 6"
        t = _Turns("end-turn-resume")
        shown = t.turn(RU)["puzzles"][0]
        t.turn(self.PASTED, fen=game)
        back = t.turn("дальше", fen=game)   # the board still shows the game
        assert back["text"].startswith("Задача 1 из 5.")
        assert back["puzzles"][0]["puzzle_id"] == shown["puzzle_id"]
        nxt = t.turn("дальше", fen=back["puzzles"][0]["fen"])   # on the puzzle now: theirs to skip
        assert nxt["text"].startswith("Задача 2 из 5.")

    def test_a_question_on_the_puzzle_itself_is_no_break(self):
        t = _Turns("end-turn-not-paused")
        shown = t.turn(RU)["puzzles"][0]
        asked = t.turn("Подскажи, с чего начать?", fen=shown["fen"])
        assert "Разминка прервана" not in asked["text"]
