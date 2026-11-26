"""The tester's ninth report (26.11), the coach's side.

1. «Почему Сxg4?» in a warm-up puzzle: «поле g4 защищено пешкой h6» — the reasons of a solution are the server's.
2. «после 4...dxe4 пешки можно разменять поровну»: a capture's outcome is the whole exchange on its square.
3. «ходом 6.Nxf3 ты вернул пешку» a pawn down: the material is counted for the comment, and «вернул» is checked.
4. «дальше» after a paused warm-up brought the next puzzle; the break was the first line of an answer about a game.
7. A question about promotion over a lesson's diagram with no pawn on it.
"""

import chess
import pytest

from src import game_mode, puzzle_facts, rule_examples, warmup
from src.answer_check import CheckContext, SentenceGate
from src.hypothetical import moved_piece_facts
from src.sessions import Session

pytestmark = pytest.mark.unit

# puzzle 3ONCq after White's Kf5: 1...Bd7+ 2.Ke4 Bxg4
PUZZLE = "8/8/2bk1p1p/2p4P/1p3PB1/1P6/2P5/8 b - - 5 50"
SOLVED = "8/8/3k1p1p/2p4P/1p2KPb1/1P6/2P5/8 w - - 0 52"


def _puzzle_start() -> str:
    board = chess.Board("8/8/2bk1p1p/2p4P/1p2KPB1/1P6/2P5/8 w - - 4 50")
    board.push_uci("e4f5")
    return board.fen()


def _issues(fen, text, student=chess.BLACK, surface=None):
    ctx = CheckContext.from_fens([fen], [], student_color=student)
    ctx.language = "ru"
    if surface:
        ctx.relation_surface = surface
    gate = SentenceGate(ctx, enabled=True)
    return [i for _, issues, _ in gate.feed(text) + gate.flush() for i in issues]


# ── 1. the solution's reasons ────────────────────────────────────────────────────────────────────────────────────
def test_every_move_of_the_solution_is_told_with_what_it_does():
    lines = puzzle_facts.solution_facts(_puzzle_start(), ["c6d7", "f5e4", "d7g4"])
    assert len(lines) == 3
    assert lines[0].startswith("50...Bd7+ (the solver's move) — bishop from c6 to d7, check")
    assert "Ke4" in lines[0]                                   # where the checked king may go
    assert lines[1].startswith("51.Ke4 (the reply)")
    last = lines[2]
    assert "takes the bishop on g4" in last
    assert "was guarded by the white king on f5" in last and "nothing guards it any more" in last
    assert "nothing can take it back: the capture wins the bishop outright" in last
    assert "h6" not in last                                    # the pawn that «guarded g4» in the report


def test_a_solution_given_in_san_and_a_broken_one():
    assert len(puzzle_facts.solution_facts(_puzzle_start(), ["Bd7+", "Ke4", "Bxg4"])) == 3
    assert puzzle_facts.solution_facts(_puzzle_start(), ["Qh5"]) == []
    assert puzzle_facts.solution_facts("not a fen", ["Bd7+"]) == []


def test_the_puzzle_block_carries_the_facts():
    from src.server import _puzzle_block

    s = Session(id="s", user_id="u")
    board = s.ensure_board()
    s.apply_board_actions([{"type": "set_puzzle", "fen": _puzzle_start(), "solution": ["c6d7", "f5e4", "d7g4"],
                            "puzzle_id": "3ONCq"}], board_id=board.id)
    block = _puzzle_block(s.active_board())
    assert "What each move of the solution does" in block and "was guarded by the white king on f5" in block
    assert "a pawn guards only the two squares diagonally ahead" in block


@pytest.mark.parametrize("text", [
    "Bxg4 выигрывает белого слона: твой слон забирает его, и белый король не может ответить взятием, потому что "
    "поле g4 защищено пешкой h6.",
    "Король не может взять, потому что поле g4 защищено пешкой h6.",
    "Король не возьмёт слона: поле g4 защищено пешкой h6.",
])
def test_a_guard_no_board_can_give_is_cut_whatever_else_the_sentence_tells(text):
    assert any("never reaches g4" in i for i in _issues(SOLVED, text))


@pytest.mark.parametrize("text", [
    "Король не может взять, потому что поле g5 защищено пешкой h6.",       # a pawn on h6 does cover g5
    "Конь с g1 выходит и атакует пешку e5.",                               # a move of that piece, not a state
    "Король не может взять: пешка h6 не защищает g4.",                     # a denial
])
def test_what_may_be_true_is_left(text):
    assert not any("never reaches" in i for i in _issues(SOLVED, text))


# ── 2. a capture's outcome ───────────────────────────────────────────────────────────────────────────────────────
def _facts(moves: str, san: str) -> str:
    before = game_mode._replay(moves.split())
    move = before.parse_san(san)
    after = before.copy(stack=False)
    after.push(move)
    return "; ".join(moved_piece_facts(before, after, move))


def test_a_pawn_taken_and_guarded_is_won_not_traded():
    facts = _facts("d4 Nf6 c4 g6 Nc3 d5 e4", "dxe4")
    assert "taking it back would lose material" in facts and "NOT a trade" in facts
    assert "an even trade" not in facts


def test_a_pawn_that_can_be_taken_back_is_a_trade_and_a_free_one_is_won_outright():
    assert "an even trade" in _facts("d4 Nf6 c4 g6 Nc3 d5 e4 dxe4 f3", "exf3")
    assert "nothing can take it back: the capture wins the pawn outright" in _facts(
        "d4 Nf6 c4 g6 Nc3 d5 e4 dxe4 f3 exf3", "Nxf3")
    # a knight for a knight still reads as an even trade (25.11)
    assert "an even trade" in _facts("e4 e5 Nf3 Nf6 Nc3 Bb4 Bc4 O-O O-O d6 d3 h6 h3 d5 Nxd5", "Nxd5")


# ── 3. the material of a comment ─────────────────────────────────────────────────────────────────────────────────
AFTER_NXF3 = "rnbqk2r/ppp1ppbp/5np1/8/2PP4/2N2N2/PP4PP/R1BQKB1R w KQkq - 1 7"


def test_the_material_is_counted_from_the_students_side():
    down = game_mode.material_words(chess.Board(AFTER_NXF3), chess.WHITE)
    assert "White 37 points, Black 38" in down and "have a pawn more" in down and "DOWN in material (by 1 point)" in down
    up = game_mode.material_words(chess.Board(AFTER_NXF3), chess.BLACK)
    assert "the student has a pawn more" in up.lower() and "UP in material" in up
    assert "the material is level" in game_mode.material_words(chess.Board(), chess.WHITE)


def test_the_comment_prompt_has_the_count():
    from src.boards import Board

    moves = "d4 Nf6 c4 g6 Nc3 d5 e4 dxe4 f3 exf3 Nxf3 Bg7".split()
    state = game_mode.new_game_state("white", 1200, "all")
    state["moves"] = moves
    state["annotations"] = [{"ply": 11, "san": "Nxf3", "verdict": "ok", "cp_loss": 0, "eval_after": -40, "best": None}]
    rec = Board(id="b", session_id="s", kind="game", fen=AFTER_NXF3, game_state=state)
    facts = game_mode.comment_prompt(rec, "ru")[1]["content"]
    assert "DOWN in material (by 1 point)" in facts and "the capture wins the pawn outright" in facts


@pytest.mark.parametrize("text, cut", [
    ("Хорошо, ходом 6.Nxf3 ты вернул пешку и развил коня.", True),
    ("Ты отыграл пешку и стоишь хорошо.", True),
    ("Ты вернул коня на f3 и забрал пешку.", False),              # the knight's way to a square
    ("Ты вернул коня в игру.", False),
    ("Ты отыграл пешку, но всё ещё на пешку позади.", False),      # the sentence says so itself
    ("Ты вернул фигуру, молодец.", False),                         # a piece back with a pawn still missing may be true
    ("Как ты хочешь вернуть пешку?", False),
])
def test_won_back_is_checked_while_the_student_is_down(text, cut):
    found = any("still down" in i for i in _issues(AFTER_NXF3, text, student=chess.WHITE, surface="game"))
    assert found is cut


def test_won_back_is_fine_on_a_level_board_and_in_a_chat_answer():
    level = "rnbqkb1r/ppp1pp1p/5np1/3p4/2PP4/2N5/PP2PPPP/R1BQKBNR w KQkq - 0 4"
    assert not any("still down" in i for i in _issues(level, "Ты вернул пешку.", student=chess.WHITE, surface="game"))
    assert not any("still down" in i for i in _issues(AFTER_NXF3, "Ты вернул пешку.", student=chess.WHITE))


# ── 4. the warm-up left and come back to ─────────────────────────────────────────────────────────────────────────
P1 = {"puzzle_id": "p1", "fen": "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1", "solution": ["d1d8"]}
P2 = {"puzzle_id": "p2", "fen": "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1", "solution": ["e1e8"]}
P3 = {"puzzle_id": "p3", "fen": "7k/6pp/8/8/8/8/6PP/R5K1 w - - 0 1", "solution": ["a1a8"]}
EXAMPLE = "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2"


def _warm():
    s = Session(id="s", user_id="u")
    warmup.start(s, [P1, P2, P3])
    s.set_board_state(P1["fen"])
    warmup.put_up(s, "p1", P1["fen"])
    return s


def test_a_puzzle_left_unsolved_for_an_example_comes_back():
    s = _warm()
    result = {"board_actions": [{"type": "set_fen", "fen": EXAMPLE}]}
    warmup.left_for(s, result)
    assert "paused" in result["warmup_note"]
    s.set_board_state(EXAMPLE)
    assert warmup.resume(s) == P1
    warmup.put_up(s, "p1", P1["fen"])          # «дальше»: it is up again
    s.set_board_state(P1["fen"])
    assert warmup.resume(s) is None            # on the board: «дальше» is the student's to skip it


def test_a_puzzle_solved_shown_or_never_seen_left_does_not_come_back():
    s = _warm()
    assert warmup.resume(s) is None                                   # on the board
    s.set_board_state(EXAMPLE)
    assert warmup.resume(s) is None                                   # the server did not see it left
    assert warmup.paused(s) == {"n": 1, "of": 3}
    assert warmup.resume(s) == P1
    solved = _warm()
    solved.set_board_state("3R2k1/5ppp/8/8/8/8/5PPP/6K1 b - - 1 1")   # the final position: solved on the board
    solved.set_board_state(EXAMPLE)
    warmup.paused(solved)
    assert warmup.resume(solved) is None
    shown = _warm()
    warmup.note_shown(shown, "p1")
    shown.set_board_state(EXAMPLE)
    warmup.paused(shown)
    assert warmup.resume(shown) is None


def test_the_break_is_the_servers_closing_line_once():
    s = _warm()
    s.set_board_state(EXAMPLE)
    place = warmup.paused(s)
    warmup.set_tail(s, place)
    line = warmup.tail_line(s, "Вот разбор твоей партии.", "ru")
    assert line == "Разминка приостановлена на задаче 1 из 3 — напиши «дальше», чтобы вернуться к ней."
    assert warmup.tail_line(s, "…", "ru") == ""                       # once
    assert warmup.paused(s) is None


def test_a_break_the_coach_was_asked_to_say_is_not_said_twice():
    s = _warm()
    warmup.left_for(s, {"board_actions": [{"type": "set_fen", "fen": EXAMPLE}]})
    assert warmup.tail_line(s, "…Разминка приостановлена на задаче 1 из 3: напиши «дальше».", "ru") == ""
    again = _warm()
    warmup.left_for(again, {"board_actions": [{"type": "set_fen", "fen": EXAMPLE}]})
    assert warmup.tail_line(again, "Взятие на проходе — особый ход пешки.", "en").startswith("The warm-up is paused at puzzle 1 of 3")


# ── 7. a rule asked about over a lesson's diagram ────────────────────────────────────────────────────────────────
ROOK_UP = "7k/8/5q2/8/2Q5/4R3/3K4/8 w - - 0 1"


def _lesson():
    return {"title": "Превращение пешки - путь к победе", "diagrams": [{"fen": ROOK_UP}],
            "board_actions": [{"type": "set_fen", "fen": ROOK_UP}], "board_hint": "The lesson's own diagram is on the board"}


def test_the_rules_own_example_goes_up_instead_of_a_diagram_that_shows_something_else():
    out = rule_examples.over(_lesson(), "Может ли пешка превратиться в короля?")
    assert out["board_actions"][0] == {"type": "set_fen", "fen": "8/4P1k1/8/8/8/8/8/4K3 w - - 0 1"}
    assert out["example"]["key_move"] == "e8=Q" and "diagrams" not in out
    assert "INSTEAD of the lesson's own diagram" in out["board_hint"]
    hidden = rule_examples.over(_lesson(), "Может ли пешка превратиться в короля?", show=False)
    assert "board_actions" not in hidden


def test_a_lesson_asked_for_a_diagram_that_shows_the_rule_and_other_questions_stay():
    lesson = _lesson()
    assert rule_examples.over(lesson, "Давай урок про превращение пешки") is lesson
    assert rule_examples.over(lesson, "Как ходит слон?") is lesson
    shows = dict(lesson, board_actions=[{"type": "set_fen", "fen": "8/4P1k1/8/8/8/8/8/4K3 w - - 0 1"}])
    assert rule_examples.over(shows, "Может ли пешка превратиться в короля?") is shows
    base = {"example": {"source": "knowledge_base", "fen": ROOK_UP}}
    assert rule_examples.over(base, "что такое пат") is base
    locked = dict(lesson, locked=True)
    assert rule_examples.over(locked, "Может ли пешка превратиться в короля?") is locked


def test_every_example_shows_its_own_rule_and_a_bare_position_shows_none():
    for example in rule_examples.EXAMPLES:
        assert rule_examples.shown_in(example, example["fen"])
        assert not rule_examples.shown_in(example, ROOK_UP)
