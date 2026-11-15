"""A question about the student's own board is answered from that board (model bench 15.11).

«Тут есть мат в один? Ладья на d8?» was read as the textbook ending «rook against king»: the turn got the
lone-rook mate method instead of the board's analysis and the coach sent the king to a square the rook covers.
«Есть ли здесь вилка?» got «tablebase: DRAW» with no word on what the fork leaves, and the lone knight was told
as «a rook ending without pawns».
"""
import chess
import pytest

from src import hypothetical
from src.board_lock import points_at_board
from src.question_position import about_own_position, endgame_theory, material_in
from src.voice_engine_note import _line_end

BACK_RANK = "6k1/5pp1/7p/8/8/8/5PPP/3R2K1 w - - 0 1"
FORK = "r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1"


@pytest.mark.unit
class TestOwnBoard:
    @pytest.mark.parametrize("message", [
        "Тут есть мат в один? Ладья на d8?",
        "Есть мат в один? Ладья на d8?",
        "Есть мат в 2 хода ферзём?",
        "Is there a mate in two with the rook?",
    ])
    def test_mate_in_n_names_no_ending(self, message):
        assert material_in(message) is None and endgame_theory(message) is None

    @pytest.mark.parametrize("message", [
        "Как тут поставить мат ладьёй?",
        "Ладьёй мат сейчас есть?",
        "Мат ферзём? На h7?",
        "Ферзь против ладьи здесь выигрывает?",
    ])
    def test_the_words_point_at_the_board(self, message):
        assert endgame_theory(message) is not None  # the material is named…
        assert about_own_position(message)          # …and the question is about the board in front of the student

    @pytest.mark.parametrize("message", [
        "Как поставить мат ладьёй?",
        "ферзь против ладьи — это выигрыш?",
        "мат двумя слонами",
        "Ладья против слона — ничья?",
        "А ладья против пешки на a7 выигрывает?",  # a square inside the textbook's own wording
    ])
    def test_a_theory_question_stays_theory(self, message):
        assert endgame_theory(message) is not None
        assert not about_own_position(message)

    def test_a_square_counts_only_when_asked(self):
        assert points_at_board("ладья на d8?") and not points_at_board("ладья на d8?", squares=False)
        assert points_at_board("а что сейчас?", squares=False)


@pytest.mark.unit
class TestWhatTheLineLeaves:
    def test_a_fork_that_leaves_a_lone_knight(self):
        told = _line_end(chess.Board(FORK), ["d5c7", "e8d7", "c7a8", "d7e6", "e1f2"], 5)
        assert "Na8" in told and "Kd7" in told and "Ke6" not in told  # as it stands when the rook is taken
        assert "enough material to mate" in told

    def test_an_ordinary_line_says_nothing(self):
        assert _line_end(chess.Board(BACK_RANK), ["d1a1", "g7g5", "g1f1"], 5) is None

    def test_a_mate_is_told_by_the_line_itself(self):
        board = chess.Board("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1")
        assert _line_end(board, ["d1d8"], 11) is None


@pytest.mark.unit
class TestTheNamedMove:
    def test_the_replies_to_its_check_are_told(self):
        board = chess.Board(BACK_RANK)
        move = board.parse_san("Rd8+")
        after = board.copy(stack=False)
        after.push(move)
        facts = " ".join(hypothetical.moved_piece_facts(board, after, move))
        assert "gives check" in facts and "king moves: Kh7" in facts

    def test_nothing_taken_is_not_material_level_again(self):
        board = chess.Board(BACK_RANK)  # White is a rook up
        told = hypothetical.line_outcome(board, board.parse_san("Rd8+"), ["Kh7", "Kf1", "h5"])
        assert told is None or "level again" not in told


GAME = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Nd4 4. Nxe5 Qg5 5. Nxf7 Qxg2 6. Rf1 Qxe4+ 7. Be2 Nf3#"


@pytest.mark.unit
class TestPastedGame:
    """The moves of a pasted game are the game, not moves the student names on the board in front of them."""

    @pytest.mark.parametrize("message,left", [
        ("Вот моя партия, где я ошибся? " + GAME, "Вот моя партия, где я ошибся?"),
        (GAME + " А если бы 5.Bxf7+?", "А если бы 5.Bxf7+?"),  # the question after the game keeps its move
        ('[Event "x"]\n[White "a"]\n\n' + GAME + " 0-1\nПочему не Nxd4?", "Почему не Nxd4?"),
        ("Можно ли сыграть Nf3?", "Можно ли сыграть Nf3?"),
    ])
    def test_the_words_around_the_game(self, message, left):
        from src.model_router import without_game

        assert without_game(message) == left

    def test_an_unlisted_move_is_not_the_main_mistake(self):
        from src.prompt_builder import review_block

        block = review_block({"total_moves": 14, "critical_moments": [
            {"move_number": 5, "side": "white", "move": "Nxf7", "type": "blunder", "eval_before": -0.28,
             "eval_after": -6.1, "best_move": "Bxf7+"}]})
        assert "5.Nxf7" in block and "not listed lost less than 1.5 pawns" in block
