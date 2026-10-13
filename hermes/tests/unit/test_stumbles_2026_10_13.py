"""2026-10-13: where the coach stumbled in a sweep of 71 new questions on production.

The game's buttons in words (resign, take back, draw, a new game) and a move that is not one; the
language of a move written alone; a famous game found inside another word; the opening named by
the book; castling after a move that chases the attacker; a forced mate said first; the puzzle's
solution on the turns after it was set; leaked markup; «епископ».
"""

import json

import chess
import pytest
from tools.registry import registry

from src import game_mode
from src.sessions import session_store
from src.tools import discover_and_register

START = chess.STARTING_FEN
CASTLE = "r2qk2r/ppp2ppp/2np1n2/4p3/2b1P3/2N2N2/PPP2PPP/R1BQK2R w KQkq - 0 8"


@pytest.fixture(autouse=True)
def _engine(monkeypatch):
    discover_and_register()
    monkeypatch.setattr(game_mode, "_engine_move", lambda fen, elo: next(iter(chess.Board(fen).legal_moves)).uci())
    monkeypatch.setattr(game_mode, "_evaluate", lambda fen, pov: (0, None))


def _call(name, args, session):
    return json.loads(registry.dispatch(name, args, session_id=session.id))


# ── the game's buttons in words ─────────────────────────────────────────────

@pytest.mark.parametrize("text,command", [
    ("Сдаюсь", "resign"), ("я сдаюсь", "resign"), ("I resign", "resign"),
    ("Ой, верни ход назад", "takeback"), ("отмени ход", "takeback"), ("можно переходить?", "takeback"),
    ("take back", "takeback"),
    ("Давай лучше начнём заново", "restart"), ("давай новую партию", "restart"), ("сыграем ещё раз", "restart"),
    ("new game", "restart"),
    ("Предлагаю ничью", "draw"), ("давай ничью", "draw"), ("I offer a draw", "draw"),
    ("это ничья?", None), ("покажи новую партию Карлсена", None), ("а если он сдастся?", None),
    ("как не сдаваться в плохой позиции и бороться до конца, если позиция хуже", None),
])
def test_game_commands_are_read_from_short_words(text, command):
    from src.game_intent import game_command

    assert game_command(text) == command


def _game(user, color="white"):
    session = session_store.create(user_id=user)
    _call("start_game", {"color": color}, session)
    return session, session.get_board(session.active_board_id)


def test_resign_in_words_ends_the_game():
    from src.server import _game_prestep

    session, board = _game("stumble-resign")
    step = _game_prestep(session, board, "Сдаюсь")
    assert step["view"]["status"] == "finished" and step["view"]["termination"] == "resign"
    assert "resigned" in step["block"]


def test_take_back_in_words_undoes_the_students_move_and_the_reply():
    from src.server import _game_prestep

    session, board = _game("stumble-takeback")
    _call("make_game_move", {"move": "e4"}, session)
    step = _game_prestep(session, board, "Ой, верни ход назад")
    assert step["view"]["moves"] == [] and step["view"]["student_to_move"]


def test_a_draw_offered_at_the_start_is_declined_and_the_game_goes_on():
    from src.server import _game_prestep

    session, board = _game("stumble-draw")
    step = _game_prestep(session, board, "Предлагаю ничью")
    assert step["view"] is None and "declined" in step["block"] and "too early" in step["block"]
    assert board.game_state["status"] == "playing"


def test_a_draw_is_agreed_when_the_engine_is_worse(monkeypatch):
    from src.server import _game_prestep

    monkeypatch.setattr(game_mode, "_evaluate", lambda fen, pov: (-300, None))
    session, board = _game("stumble-draw-worse")
    step = _game_prestep(session, board, "Предлагаю ничью")
    assert step["view"]["result"] == "1/2-1/2" and step["view"]["termination"] == "draw"


def test_a_new_game_in_words_starts_one_with_the_same_colour():
    from src.server import _game_prestep

    session, board = _game("stumble-restart", color="black")
    step = _game_prestep(session, board, "Давай лучше начнём заново")
    assert step["view"]["board_id"] != board.id and step["view"]["student_color"] == "black"
    # after a finished game too («давай ещё раз»)
    new = session.get_board(step["view"]["board_id"])
    game_mode.resign(session, new)
    again = _game_prestep(session, new, "сыграем ещё раз")
    assert again["view"]["status"] == "playing" and again["view"]["board_id"] != new.id


def test_a_move_that_is_no_legal_move_is_said_so():
    from src.server import _game_prestep

    session, board = _game("stumble-illegal")
    step = _game_prestep(session, board, "Кe5")
    assert step["view"] is None and "Not a legal move" in step["block"] and "Nf3" in step["block"]


def test_the_game_action_tool_does_what_the_words_ask():
    session, board = _game("stumble-tool")
    _call("make_game_move", {"move": "d4"}, session)
    out = _call("game_action", {"said": "отмени ход"}, session)
    assert out["ok"] and out["action"] == "takeback" and out["board_actions"][0]["game"]["moves"] == []
    assert "do not ask" in _call("game_action", {"said": "как дела"}, session)["error"]
    out = _call("game_action", {"action": "resign"}, session)
    assert out["board_actions"][0]["game"]["termination"] == "resign"


def test_game_action_is_offered_to_the_text_coach():
    from src.tool_selector import CORE_TOOLS

    assert "game_action" in CORE_TOOLS


# ── language, famous games, opening name ────────────────────────────────────

@pytest.mark.parametrize("move", ["e2-e4", "Ng1-f3", "e7-e8=Q", "g1f3", "exd5!?", "O-O-O+"])
def test_a_move_written_alone_carries_no_language(move):
    from src.prompt_builder import _script_language, conversation_language

    assert _script_language(move) is None
    assert conversation_language([move, "Сыграем партию? Я за белых"], "ru")[0] == "ru"


def test_a_famous_game_is_named_from_the_start_of_a_word():
    from src.famous_games import famous_game

    assert famous_game("У меня кончилось время, а у соперника остался только король. Кто победил?") is None
    assert famous_game("Покажи оперную партию Морфи")["key"] == "opera"


def test_the_opening_is_named_by_the_book_from_the_position():
    from src.prompt_builder import build_system_prompt  # noqa: F401 — the module loads
    from src.voice_engine_note import _opening

    assert "Queen's Gambit Declined" in _opening("rnbqkbnr/ppp2ppp/4p3/3p4/2PP4/8/PP2PPPP/RNBQKBNR w KQkq - 0 3")


# ── castling, mate, the puzzle ──────────────────────────────────────────────

def test_castling_says_where_a_chased_attacker_still_bars_it():
    from src.board_rules import castling_facts

    facts = castling_facts(chess.Board(CASTLE))[0]
    assert "Ba6" in facts and "Bb5" in facts and "still attack f1" in facts
    assert "the white bishop on c1, the white queen on d1, and nothing else stands there" in facts
    assert castling_facts(chess.Board()) == []


def test_castling_after_a_named_move_is_checked():
    from src.prompt_builder import moves_in_question_block

    block = moves_in_question_block("А если сначала сыграть b3, потом рокировка будет?", CASTLE)
    b3 = next(line for line in block.splitlines() if line.startswith("- b3"))
    assert "castling after it" in b3 and "Ba6" in b3


def test_a_forced_mate_heads_the_engine_block():
    from src.prompt_builder import engine_note_block

    block = engine_note_block("[Engine] … Best: Bxf7+ (mate in 2 for White; line Bxf7+ Ke7 Nd5#).", mate_in=2,
                              fen="rn1qkbnr/ppp2p1p/3p2p1/4N3/2B1P3/2N5/PPPP1PPP/R1BbK2R w KQkq - 0 6")
    assert "FORCED MATE IN 2 for White" in block.split("\n")[1]
    assert "FORCED MATE" not in engine_note_block("[Engine] …", mate_in=None)
    assert "FORCED MATE" not in engine_note_block("[Engine] …", mate_in=-2)  # the side to move is mated


def test_the_puzzle_on_the_board_keeps_its_solution_for_the_next_turns():
    from src.boards import Board
    from src.server import _puzzle_block

    board = Board(session_id="s")
    board.apply_action({"type": "set_puzzle", "fen": "1r2rk2/p1Q3Rp/5p2/8/2q2p2/P7/2P2PPP/5RK1 b - - 2 27",
                        "solution": ["Qxf1+", "Kxf1", "Rb1#"], "puzzle_id": "x"})
    block = _puzzle_block(board)
    assert "solution: Qxf1+ Kxf1 Rb1#" in block and "not started" in block
    b = chess.Board(board.fen)
    b.push_san("Qxf1+")
    b.push_san("Kxf1")
    board.fen = b.fen()
    assert "next is Rb1#" in _puzzle_block(board)
    board.apply_action({"type": "set_fen", "fen": "8/8/8/8/8/8/8/K6k w - - 0 1"})
    assert _puzzle_block(board) == ""


# ── the text itself ─────────────────────────────────────────────────────────

def test_leaked_markup_without_string_is_stripped():
    from src.answer_check import strip_leaks

    assert strip_leaks('="true">Nepomniachtchi\n\nЭта партия не нашлась') == "\n\nЭта партия не нашлась"
    assert strip_leaks("Это true и false.") == "Это true и false."


def test_bishop_is_a_bishop():
    from src.answer_check import chess_terms

    assert chess_terms("У белых епископ и конь; матовать конём и епископом. Епископы сильны.") == \
        "У белых слон и конь; матовать конём и слоном. Слоны сильны."


def test_a_pinned_piece_is_named_as_pinned_not_as_unable_to_reach():
    from src.prompt_builder import moves_in_question_block

    block = moves_in_question_block("Могу я пойти конём на e4?",
                                    "rnbqk1nr/pppp1ppp/4p3/8/1b1P4/2N5/PPP1PPPP/R1BQKBNR w KQkq - 2 3")
    assert "the knight on c3 could go there, but it is pinned to its king by the bishop on b4" in block


def test_castling_said_without_its_word_is_checked():
    from src.prompt_builder import moves_in_question_block

    assert "O-O-O: NOT legal — pieces stand between" in moves_in_question_block("А в длинную можно?", CASTLE)
    assert moves_in_question_block("Как играть в длинную партию?", CASTLE) == ""


@pytest.mark.parametrize("question,rule", [
    ("У меня кончилось время, а у соперника остался только король. Кто победил?", "Time:"),
    ("Позиция повторилась три раза, но не подряд. Это ничья?", "Repetition:"),
    ("Можно ли рокироваться, если раньше мне уже давали шах, но король не двигался?", "Castling is illegal only"),
    ("Можно рокироваться в длинную? Поле b1 же бьёт чёрная ладья.", "Castling is illegal only"),
    ("Можно ли взять на проходе слоном или конём?", "En passant:"),
    ("Можно ли превратить пешку во второго ферзя, если мой ферзь ещё на доске?", "Promotion:"),
    ("Что такое правило 50 ходов?", "Fifty moves:"),
])
def test_a_rules_question_gets_the_rule(question, rule):
    from src.rules_facts import rules_block

    assert rule in rules_block(question)


@pytest.mark.parametrize("question", ["Какой ход лучше?", "Покажи пример связки", "Повтори, пожалуйста, можно?",
                                      "Патша қай жерде? Бұл ереже ме?"])
def test_other_questions_get_no_rule(question):
    from src.rules_facts import rules_block

    assert "Repetition" not in rules_block(question) and "Stalemate" not in rules_block(question)


def test_an_attacked_rook_square_does_not_bar_long_castling():
    from src.board_rules import castling_facts

    assert "b1 is attacked, but only the rook passes it" in castling_facts(chess.Board("1r2k3/8/8/8/8/8/8/R3K2R w KQ - 0 1"))[0]


def test_an_answer_never_starts_on_a_dangling_connective():
    from src.answer_check import strip_leaning_start

    assert strip_leaning_start("Зато есть сильный ход Nc3: он нападает на коня.").startswith("Есть сильный ход")
    assert strip_leaning_start("Но ничья наступает не сама по себе.").startswith("Ничья наступает")
    assert strip_leaning_start("Дело в том, что пешка h3 нападала на коня.").startswith("Пешка h3")
    assert strip_leaning_start("Новый план — играть d4.") == "Новый план — играть d4."


def test_mate_in_n_denied_with_a_verb_is_a_denial():
    from src.answer_check import CheckContext
    from src.answer_check_rules import _mate_in_issues

    ctx = CheckContext.from_fens("r1bq1b1r/ppp3pp/2n1k3/3np3/2B5/5Q2/PPPP1PPP/RNB1K2R w KQ - 2 8")
    ctx.engine_eval = 0.9
    assert _mate_in_issues("Мат в два тут не форсируется — король на e6 пока хорошо прикрыт.", ctx) == []


def test_a_numbered_move_is_checked_at_that_move_of_the_game():
    from src.answer_check import CheckContext, check_sentence

    ctx = CheckContext.from_fens("r1b1kbnr/pppp1Npp/8/8/4q3/5n2/PPPPBP1P/RNBQKR2 w Qkq - 2 8")
    ctx.add_line("1. e4 e5 2. Nf3 Nc6 3. Bc4 Nd4 4. Nxe5 Qg5 5. Nxf7 Qxg2 6. Rf1 Qxe4+ 7. Be2 Nf3#")
    assert "not possible at move 5" in check_sentence("Правильный ход на 5-м: **5. Nxd4!**", ctx)[0]
    assert check_sentence("Надо было **4. Nxd4 exd4** и спокойная игра.", ctx) == []
    assert check_sentence("Лучше было 4. Nxd4 exd4 5. O-O.", ctx) == []


def test_the_tablebase_names_every_move_that_keeps_the_result():
    from src.board_rules import tablebase_facts

    board = chess.Board("8/8/8/P3k3/8/8/8/7K b - - 0 1")
    tb = {"category": "draw", "best_san": "Kd5", "best_category": "draw", "keeping": ["Kd5", "Kd6"]}
    assert "the moves that hold the draw for Black: Kd5, Kd6 — every other move loses" in tablebase_facts(board, tb)[0]
