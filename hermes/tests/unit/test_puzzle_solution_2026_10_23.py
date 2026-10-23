"""2026-10-23, the full production run: four more things the model got wrong that the system can know.

* the puzzle's solution asked for («Сдаюсь, покажи решение») — the system shows it and the model says that line
  (src/tools/puzzles.puzzle_solution, src/intent «solution», src/server solution step, src/answer_check);
* a fork available now is a fact of the position (src/position_facts.fork_facts) — «вилки нет» with Nc7+;
* «ферзь b6 у тебя висит» with no queen on b6 (src/answer_check._GHOST);
* game 6 of the 2021 title match is a famous game with a verified score (src/famous_games) — «вничью»."""

import json
from unittest.mock import MagicMock, patch

import chess
import pytest
from fastapi.testclient import TestClient

from src.answer_check import CheckContext, check_sentence
from src.famous_games import famous_game
from src.intent import read_intent
from src.position_facts import fork_facts, static_facts
from src.server import app, session_store
from src.tools.puzzles import _handle_puzzle_solution, asks_solution, numbered_line, solution_line
from src.user_profile import UserProfile

MATE2 = "3rkr2/1Qpb4/p1B1pq2/7p/3PN1p1/B1P3P1/P4nKP/R4R2 b - - 3 24"   # d2-puzzle of the 71 set: Qf3+ Kg1 Nh3#
SOLUTION = ["Qf3+", "Kg1", "Nh3#"]
FORK = "r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1"                             # «Есть ли здесь вилка?» — Nc7+
NO_FORK = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
START = chess.STARTING_FEN


# ── the words ───────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,asks", [
    ("Сдаюсь, покажи решение", True), ("не знаю. дай подсказку", False), ("Не знаю", True), ("какое решение?", True),
    ("скажи ответ", True), ("I give up", True), ("show me the solution", True), ("сдаюсь, давай следующую", False),
    ("не знаю, дай другую задачу", False), ("а если Qf3?", False), ("что здесь делать?", False), ("берілемін", True),
])
def test_the_words_that_give_up(text, asks):
    assert asks_solution(text) is asks


def test_the_intent_is_solution_only_with_a_puzzle_on_the_board():
    assert read_intent("Сдаюсь, покажи решение", fen=MATE2, puzzle_on_board=True) == {"kind": "solution"}
    assert read_intent("Сдаюсь, покажи решение", fen=MATE2)["kind"] != "solution"
    assert read_intent("сдаюсь, давай следующую", fen=MATE2, puzzle_on_board=True, puzzle_queue=True)["kind"] == "puzzle"
    assert read_intent("Сдаюсь", fen=START, live_game=True)["kind"] == "game_command"   # a game: resign, not a solution


# ── the solution of the puzzle on the board ────────────────────────────────────────────────────

def _puzzle_session(user="solution-user", fen=MATE2, solution=SOLUTION):
    session = session_store.create(user)
    board = session.ensure_board()
    session.apply_board_actions([{"type": "set_puzzle", "fen": fen, "solution": solution, "puzzle_id": "t1"}], board_id=board.id)
    return session, session.get_board(session.active_board_id)


def test_the_solution_line_from_the_start_and_part_way():
    session, board = _puzzle_session()
    sol = solution_line(board)
    assert sol["sans"] == SOLUTION and sol["reached"] == 0 and sol["next"] == SOLUTION
    assert numbered_line(MATE2, SOLUTION) == "24...Qf3+ 25.Kg1 Nh3#"
    b = chess.Board(MATE2)
    b.push_san("Qf3+")
    b.push_san("Kg1")
    board.fen = b.fen()   # the page syncs the student's moves into the board (PATCH), the puzzle stays
    sol = solution_line(board)
    assert sol["reached"] == 2 and sol["next"] == ["Nh3#"]
    assert solution_line(session.ensure_board()) is not None


def test_the_tool_shows_the_solution_with_arrows_and_the_exact_line():
    session, _ = _puzzle_session("solution-tool")
    out = json.loads(_handle_puzzle_solution({}, session_id=session.id, user_id="solution-tool"))
    assert out["ok"] and out["line"] == "24...Qf3+ 25.Kg1 Nh3#" and out["moves"] == SOLUTION
    arrows = out["board_actions"][0]
    assert arrows["type"] == "draw_arrows" and [a["from"] + a["to"] for a in arrows["arrows"]] == ["f6f3", "g2g1", "f2h3"]
    assert "Say it EXACTLY" in out["note"] and "Nh3#" in out["note"]
    empty = session_store.create("no-puzzle")
    assert "error" in json.loads(_handle_puzzle_solution({}, session_id=empty.id, user_id="no-puzzle"))


def test_the_turn_shows_the_solution_before_the_first_word_and_hands_the_model_the_line():
    client = TestClient(app)
    user = {"X-User-Id": "solution-turn"}
    sid = client.post("/api/coach/sessions", headers=user).json()["id"]
    session = session_store.get(sid, "solution-turn")
    board = session.ensure_board()
    session.apply_board_actions([{"type": "set_puzzle", "fen": MATE2, "solution": SOLUTION, "puzzle_id": "t1"}], board_id=board.id)
    seen = {}
    with patch("src.server._create_agent") as mock_agent, patch("src.server.load_user_profile") as mock_profile:
        mock_profile.return_value = UserProfile(user_id="solution-turn")
        agent = MagicMock()

        def _chat(message, stream_callback=None):
            seen["message"] = message
            if stream_callback:
                stream_callback("Решение: 24...Qf3+ 25.Kg1 Nh3#. Конь закрывает последнее поле.")
            return "ok"

        agent.chat.side_effect = _chat
        mock_agent.return_value = agent
        resp = client.post("/api/coach/chat", headers=user, json={"message": "Сдаюсь, покажи решение", "session_id": sid, "fen": MATE2})
        assert resp.status_code == 200
    frames = [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: ")]
    kinds = [next(iter(f)) for f in frames]
    arrows = [f for f in frames if "board_actions" in f and f["board_actions"][0].get("type") == "draw_arrows"]
    assert arrows and kinds.index("board_actions") < kinds.index("delta")
    assert "the system has SHOWN it on the board" in seen["message"] and "24...Qf3+ 25.Kg1 Nh3#" in seen["message"]
    assert "Nh3#" in resp.text


# ── the answer check knows the solution ────────────────────────────────────────────────────────

def _ctx():
    ctx = CheckContext.from_fens([MATE2], question="Сдаюсь, покажи решение")
    ctx.puzzle_solution = SOLUTION
    return ctx


@pytest.mark.parametrize("sentence", [
    "Решение такое: сначала шах ферзём на f3, а затем мат ферзём на h1 — Qf3+ Kg1 Qh1#.",
    "После Qf3+ Kg1 ферзь на h1 ставит мат.",
    "The solution is Qf3+ Kg1 Qh1#.",
])
def test_another_finish_given_as_the_solution_is_not_shown(sentence):
    issues = check_sentence(sentence, _ctx())
    assert issues and "Nh3#" in issues[0], issues


@pytest.mark.parametrize("sentence", [
    "Решение: 24...Qf3+ 25.Kg1 Nh3# — конь закрывает последнее поле.",
    "Начни с шаха ферзём по третьей горизонтали.",
    "Qh1 здесь не мат — король просто заберёт ферзя.",
    "Если бы король был на h1, то Qf1 был бы матом, но он на g2.",
])
def test_the_puzzles_own_line_and_hints_pass(sentence):
    assert check_sentence(sentence, _ctx()) == []


# ── a fork is a fact of the position ───────────────────────────────────────────────────────────

def test_a_fork_available_now_is_in_the_facts():
    facts = fork_facts(chess.Board(FORK))
    assert facts and facts[0].startswith("a fork is available now: Nc7+ attacks") and "(with check)" in facts[0]
    assert "black king e8" in facts[0] and "black rook a8" in facts[0]
    assert any("fork is available" in f for f in static_facts(chess.Board(FORK)))
    assert fork_facts(chess.Board(NO_FORK)) == []
    # a fork from a square where the piece is simply taken is not one
    assert fork_facts(chess.Board("4k3/8/8/8/8/8/3q4/3NK3 w - - 0 1")) == []   # Nc3/Ne3 would hit the queen only


# ── «ферзь b6 у тебя висит» ─────────────────────────────────────────────────────────────────────

def test_a_ghost_with_words_between_the_square_and_the_verb():
    fen = "r1b1kbnr/pppp1Npp/8/8/2BnP3/8/PPPP1PqP/RNBQKR2 b Qkq - 1 6"   # black-best of the 71 set: the queen is on g2
    issues = check_sentence("Ферзь b6 у тебя висит под боем коня f7, так что медлить нельзя.", CheckContext.from_fens([fen]))
    assert issues and "no queen on b6" in issues[0]
    assert check_sentence("Ферзь g2 у тебя уже бьёт e4 и h2.", CheckContext.from_fens([fen])) == []


# ── game 6 of the 2021 match ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "Покажи 6-ю партию матча Карлсен — Непомнящий 2021 года",
    "покажи шестую партию Карлсена с Непомнящим",
    "самая длинная партия Карлсен — Непомнящий",
    "show game 6 Carlsen Nepomniachtchi",
])
def test_game_six_of_dubai_is_known(text):
    g = famous_game(text)
    assert g and g["key"] == "wch2021-g6" and "136.Ng7" in g["block"] and "1-0" in g["block"]
    board = chess.Board()
    for san in g["pgn"].split("\n\n")[-1].replace("1-0", "").split():
        if "." in san:
            san = san.split(".")[-1]
        if san:
            board.push_san(san)
    assert board.fullmove_number == 136 and board.turn == chess.BLACK and board.piece_at(chess.G7).piece_type == chess.KNIGHT


def test_another_game_of_that_match_is_not_game_six():
    assert famous_game("покажи 2-ю партию матча Карлсен — Непомнящий") is None
    assert famous_game("Карлсен и Непомнящий играли в Дубае") is None
