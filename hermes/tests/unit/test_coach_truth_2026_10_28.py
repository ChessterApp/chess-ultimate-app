"""Stand run 28.10 (theory set, text games, voice): what the coach still made up after the moves were right — traps
told from memory, attacks and defences in reverse word order, the engine's move given to the student, a variation
named wrongly, a made-up opening position put on the board. Each closed by what the server knows."""

import json

import chess
import pytest

from src.answer_check import CheckContext, check_sentence
from src.game_intent import spoken_squares
from src.hypothetical import line_outcome


def _board(moves: str) -> chess.Board:
    board = chess.Board()
    for san in moves.split():
        board.push_san(san)
    return board


# ── a move asked about: where the engine's line leads, in words ───────────────────────────────────────────────

ELEPHANT = "d4 d5 c4 e6 Nc3 Nf6 Bg5 Nbd7 cxd5 exd5"


@pytest.mark.unit
def test_the_elephant_trap_line_ends_in_a_knight_for_a_pawn():
    board = _board(ELEPHANT)
    move = board.parse_san("Nxd5")
    after = board.copy()
    after.push(move)
    reply = "Nxd5 Bxd8 Bb4+ Qd2 Bxd2+ Kxd2 Kxd8".split()
    assert line_outcome(board, move, reply, 0.4, -5.6) == "At the end of this line White has given a knight for a pawn."


@pytest.mark.unit
def test_a_line_that_stops_on_a_check_is_judged_by_the_evaluation():
    board = _board("e4 e5 Nf3 Nc6 Bc4 Nd4")  # Blackburne-Shilling
    move = board.parse_san("Nxe5")
    out = line_outcome(board, move, ["Qg5", "Bxf7+"], 1.4, -0.8)
    assert out.startswith("The line is not settled") and "White is worse" in out


@pytest.mark.unit
def test_a_sacrifice_with_compensation_is_not_counted_as_material():
    board = _board("e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5")  # the Fried Liver: 5...Nxd5 6.Nxf7 Kxf7 is White's attack
    move = board.parse_san("Nxd5")
    out = line_outcome(board, move, ["Nxf7", "Kxf7", "Qf3+", "Ke6"], 0.1, 0.9)
    assert out.startswith("The line is not settled")


# ── the coach's words checked against the board ────────────────────────────────────────────────────────────────

def _ctx(moves: str, question: str = "", game: bool = False, student_black: bool = False) -> CheckContext:
    board = _board(moves)
    ctx = CheckContext.from_fens([board.fen()], question=question)
    if game:
        ctx.game_moves = moves.split()
        ctx.game_engine_moves = moves.split()[0 if student_black else 1::2]
        ctx.student_color = chess.BLACK if student_black else chess.WHITE
    return ctx


@pytest.mark.unit
@pytest.mark.parametrize("moves, text, wrong", [
    ("e4 c6 d4 d5 c3 a5 Nf3 dxe4 Bc4 exf3", "А ещё твоя пешка f2 — её тоже бьёт эта же пешка f3, а защищена только королём.",
     "a pawn on f3 does not attack f2"),
    ("e3 e5 Nc3", "Пешку e5 пока держат только пешка d7 и конь g8.", "a knight on g8 does not attack e5"),
])
def test_attacks_and_defences_in_reverse_word_order_are_read_back(moves, text, wrong):
    assert wrong in check_sentence(spoken_squares(text), _ctx(moves))


@pytest.mark.unit
def test_a_king_held_by_pieces_is_no_attack_on_its_square():
    ctx = _ctx("e4 e5")
    ctx = CheckContext.from_fens(["kB6/8/1PK5/8/8/8/8/8 w - - 0 1"])
    assert not check_sentence("Король чёрных заперт на a8 — его держат твоя пешка b6 и король c8.", ctx)


@pytest.mark.unit
def test_the_engines_move_given_to_the_student_is_read_back():
    ctx = _ctx("e3 e5 d4", game=True, student_black=True)
    assert any("was the engine's" in i for i in check_sentence("Принято, твой ход d4.", ctx))
    assert not check_sentence("Сейчас твой ход: подумай про d5.", _ctx("e3 e5 d4", game=True, student_black=True))


@pytest.mark.unit
@pytest.mark.parametrize("moves, question, text, real", [
    ("e4 c6 d4 d5 e5", "Какой это дебют и какой вариант?", "Это защита Каро-Канн, вариант Атака Панова.", "Advance Variation"),
    ("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6", "Что тут лучше?", "Здесь у нас вариант дракона.", "Najdorf"),
])
def test_a_wrong_opening_named_for_the_board_is_read_back(moves, question, text, real):
    issues = check_sentence(text, _ctx(moves, question))
    assert any("opening on the board" in i and real in i for i in issues)


@pytest.mark.unit
@pytest.mark.parametrize("moves, question, text", [
    ("e4 c6 d4 d5 e5", "Расскажи про атаку Панова", "Это защита Каро-Канн, вариант Атака Панова."),  # the line asked about
    ("e4 c6 d4 d5 e5", "Какой это дебют?", "Это Каро-Канн. Не путай с атакой Панова."),          # a hedge
    ("d4 d5 Bf4", "What opening is this?", "This is the Accelerated London System."),             # the real name
    ("e4 e5 Nf3 Nc6 Bc4 Bc5", "Как называется этот дебют?", "Это итальянская партия, джуоко пиано."),
])
def test_right_or_other_line_opening_names_pass(moves, question, text):
    assert not [i for i in check_sentence(text, _ctx(moves, question)) if "opening on the board" in i]


# ── a made-up position the model sets on the board ─────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_an_invented_opening_position_does_not_go_up_and_a_verified_one_does():
    import src.server  # noqa: F401 — registers the tools with their wrappers
    from tools.registry import registry

    from src.sessions import session_store

    session = session_store.create("truth")
    kw = {"session_id": session.id, "user_id": "truth"}
    made_up = "rnbqkbnr/ppp1pppp/8/8/4p3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 3"  # stand voice run 28.10
    out = json.loads(registry.dispatch("board_control", {"action_type": "set_fen", "fen": made_up}, **kw))
    assert out.get("shown") is False
    registry.dispatch("lookup_opening", {"question": "что такое ловушка Легаля"}, **kw)
    on_the_line = _board("e4 e5 Nf3 d6 Bc4 Bg4 Nc3 g6").fen()
    out = json.loads(registry.dispatch("board_control", {"action_type": "set_fen", "fen": on_the_line}, **kw))
    assert out["board_actions"][0]["fen"] == on_the_line
    ending = "8/8/8/4k3/8/8/4P3/4K3 w - - 0 1"  # a sparse set-up stays the model's to set
    out = json.loads(registry.dispatch("board_control", {"action_type": "set_fen", "fen": ending}, **kw))
    assert out["board_actions"][0]["fen"] == ending


# ── the game told move by move: what the moved piece does, what blocks what, the move as the attacker ─────────

def _told(moves: str, text: str) -> list:
    board = _board(moves)
    ctx = CheckContext.from_fens([board.fen()])
    ctx.add_line(moves)
    ctx.game_moves = moves.split()
    return check_sentence(spoken_squares(text), ctx)


@pytest.mark.unit
@pytest.mark.parametrize("moves, text, wrong", [
    ("e4 e5 Nf3 Nc6 Bc4 Nf6", "3...Кf6 — конь вышел и прикрыл f7, это итальянская партия.", "a knight on f6 does not attack f7"),
    ("e4 e5 Nf3 Nc6 Bc4 Nf6 d3 Be7", "Соперник ответил 4...Be7: слон с f8 поднялся на e7 и прикрыл f7.", "a bishop on e7 does not attack f7"),
    ("e4 e5 Nf3 d6", "Его пешка e5 теперь защищена, но зато d6 перекрыла дорогу слону c8.", "d6 is not on any line of the bishop on c8"),
    ("e4 e6", "Белые захватывают центр пешкой на е4, а чёрные сразу её атакуют ходом е6.", "after e6 the piece that moved does not attack e4"),
])
def test_told_moves_that_do_not_do_what_is_said_are_read_back(moves, text, wrong):
    assert any(wrong in i for i in _told(moves, text))


@pytest.mark.unit
@pytest.mark.parametrize("moves, text", [
    ("e4 e5 Nf3 Nc6", "2...Кc6 — конь вышел и прикрыл e5."),
    ("e4 e5 Nf3 Nc6 Bc4", "3.Сc4 — слон вышел на c4 и нацелился на f7."),
    ("e4 e5 Nf3 d6", "Пешка d6 закрыла слону f8 диагональ."),
    ("e4 e5 Nf3 Nc6 Bc4 Nf6", "Слон f8 заперт пешкой e7."),
    ("d4 d5 c4", "Белые атакуют пешку d5 ходом c4."),
])
def test_told_moves_that_are_true_pass(moves, text):
    assert not _told(moves, text)
