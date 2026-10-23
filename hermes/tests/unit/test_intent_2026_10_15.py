"""2026-10-15: what the student wants, decided in one place for text and voice (src/intent.py)."""

import chess
import pytest

from src.intent import read_intent

POS = "r2q1rk1/pp2bppp/4bn2/3P4/8/2N2N2/PP2BPPP/R2Q1RK1 b - - 0 12"
GAME = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
LONG_PGN = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Nc3 Bc5 5. d3 d6 6. O-O O-O"


@pytest.mark.parametrize("text,kind", [
    ("Дай мне тактическую задачу", "puzzle"),         # the chip the voice gate missed (09.10)
    ("Give me a tactical puzzle", "puzzle"),
    ("задачу на вилку", "puzzle"),
    ("Давай сыграем, я чёрными", "game_request"),
    ("Покажи оперную партию Морфи", "famous_game"),
    ("покажи жареную печень", "opening"),
    ("что такое связка", "concept"),
    ("почему здесь связка", "board"),                   # about the student's position: nothing replaces it
    ("какой здесь лучший ход?", "board"),
    ("привет", "none"),
])
def test_what_the_words_ask_for_outside_a_game(text, kind):
    assert read_intent(text, fen=POS)["kind"] == kind


def test_the_puzzle_theme_and_solving_the_puzzle_already_on_the_board():
    assert read_intent("задачу на вилку", fen=POS)["theme"] == "вилку"
    assert read_intent("реши задачу", fen=POS, puzzle_on_board=True)["kind"] == "board"
    assert read_intent("реши задачу", fen=chess.STARTING_FEN)["kind"] == "puzzle"


@pytest.mark.parametrize("text,kind,extra", [
    ("Хорошо, слон c4", "move", {"san": "Bc4"}),
    ("Слон c4?", "move", {"san": "Bc4"}),               # a rising voice is no question
    ("слон си четыре", "move", {"san": "Bc4"}),
    ("А если слон c4?", "idea", {"moves": ["Bc4"]}),
    ("e4 хорош?", "none", {}),                          # an idea about a move not playable here
    ("Сдаюсь", "game_command", {"command": "resign"}),
    ("покажи пример вилки", "none", {}),                # the board is the game's
])
def test_in_a_game(text, kind, extra):
    out = read_intent(text, fen=GAME, live_game=True)
    assert out["kind"] == kind and all(out.get(k) == v for k, v in extra.items()), out


def test_a_new_game_after_one_ended_takes_the_named_colour():
    out = read_intent("сыграем ещё раз чёрными", fen=GAME, finished_game=True)
    assert out == {"kind": "game_command", "command": "restart", "color": "black"}
    assert read_intent("Сдаюсь", fen=GAME)["kind"] != "game_command"   # no game, nothing to resign


def test_a_review_needs_a_game_on_the_board():
    assert read_intent("разбери мою партию, я играл чёрными", pgn=LONG_PGN)["kind"] == "review"
    assert read_intent("разбери мою партию, я играл чёрными", pgn=LONG_PGN)["side"] == "black"
    assert read_intent("разбери мою партию", pgn="1. e4 e5")["kind"] != "review"


def test_the_endpoint_reads_the_game_from_the_session(monkeypatch):
    from fastapi.testclient import TestClient

    from src import game_mode, server
    from src.sessions import session_store

    monkeypatch.setattr(game_mode, "_engine_move", lambda fen, elo: next(iter(chess.Board(fen).legal_moves)).uci())
    monkeypatch.setattr(game_mode, "_evaluate", lambda fen, pov: (0, None))
    session = session_store.create(user_id="intent-endpoint")
    game_mode.start_game(session, "white", 1200, "quiet")
    client = TestClient(server.app)
    out = client.post("/api/coach/voice/intent", headers={"X-User-Id": "intent-endpoint"},
                      json={"text": "е два е четыре", "session_id": session.id}).json()
    assert out == {"kind": "move", "san": "e4"}

# 23.10, Alexander's voice test: «Да, поставь, пожалуйста, позицию на связку» was nobody's request — the model
# only said «посмотри на эту позицию» and the board stayed. A position or an example asked for by theme is a
# puzzle of that theme (src/intent._POSITION_ON); the board itself is never a theme.
@pytest.mark.parametrize("text,theme", [
    ("Да, по- поставь, пожалуйста, а-а позицию на связку.", "связку"),
    ("поставь позицию на связку", "связку"),
    ("покажи пример на вилку", "вилку"),
    ("Хочу позицию со связкой", "связкой"),
    ("можно пример про двойной удар?", "двойной удар"),
    ("Put up a position on pins", "pins"),
])
def test_a_position_or_example_asked_for_by_theme_is_a_puzzle(text, theme):
    assert read_intent(text, fen=POS) == {"kind": "puzzle", "theme": theme}


@pytest.mark.parametrize("text,kind", [
    ("в этой позиции на доске что делать?", "board"),
    ("объясни позицию на доске", "board"),
    ("какой лучший ход в этой позиции на связку?", "board"),
    ("поставь позицию на доске заново", "none"),
    ("Нет. Нет, не вижу. Ты не поменял доску.", "none"),
])
def test_the_board_itself_is_not_a_theme(text, kind):
    assert read_intent(text, fen=POS)["kind"] == kind
