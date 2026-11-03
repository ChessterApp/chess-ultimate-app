"""R2 03.11 (verify1102b VERDICT §6 R2): a line named as a line goes to the engine stage again.

K3 (02.11) read every written move between a candidate and its praise as the other side's reply, so the praise was the
reply's and nothing was proposed. That was right for «После Qxd4 c5 …» (trap-noah) but it also took «Линия dxe5 dxe5
Nxe5 выигрывает пешку» and «Вариант Bxf7+ … выигрывает белым ферзя» (fresh-miss-2 L06, L12), where the praise is the
named line's outcome for the side that starts it, and main hands the first move to the engine. Boards and wordings
here are new: the Giuoco Piano, the Queen's Gambit Declined (the Elephant trap), 3...d6 in the Italian, the Najdorf
after 6.Be2, the Four Knights fork trick.
"""

import chess
import pytest

from src.answer_check import CheckContext, check_sentence, proposed_move


def _fen(*sans: str) -> str:
    board = chess.Board()
    for san in sans:
        board.push_san(san)
    return board.fen()


GIUOCO = _fen("e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "c3", "Nf6")                          # White to move
QGD = _fen("d4", "d5", "c4", "e6", "Nc3", "Nf6", "Bg5", "Nbd7")                               # White: the Elephant trap
ITAL_D6 = _fen("e4", "e5", "Nf3", "Nc6", "Bc4", "d6")                                         # White: Nxe5? loses a piece
NAJDORF = _fen("e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6", "Be2")      # Black to move
FORK_TRICK = _fen("e4", "e5", "Nf3", "Nc6", "Nc3", "Nf6", "Bc4")                              # Black: Nxe4 Nxe4 d5


def _proposed(fen: str, sentence: str, **ctx_kw):
    ctx = CheckContext.from_fens([fen])
    for k, v in ctx_kw.items():
        setattr(ctx, k, v)
    found = proposed_move(sentence, ctx)
    return found[2] if found else None


class TestANamedLineIsHandedToTheEngine:
    @pytest.mark.parametrize("fen, sentence, san", [
        (GIUOCO, "Линия Bxf7+ Kxf7 Ng5+ Kg8 выигрывает белым пешку.", "Bxf7+"),
        (GIUOCO, "Вариант Bxf7+ Kxf7 Ng5+ Kg8 — и белые выигрывают пешку.", "Bxf7+"),
        (ITAL_D6, "Комбинация Nxe5 Nxe5 Qh5 выигрывает белым фигуру.", "Nxe5"),
        (ITAL_D6, "Последовательность ходов Nxe5 Nxe5 Qh5 выигрывает белым фигуру.", "Nxe5"),
        (ITAL_D6, "The line Nxe5 Nxe5 Qh5 wins a piece for White.", "Nxe5"),
        (NAJDORF, "Линия Nxe4 Nxe4 d5 выигрывает чёрным фигуру назад.", "Nxe4"),
        (FORK_TRICK, "The continuation Nxe4 Nxe4 d5 wins the piece back for Black.", "Nxe4"),
        (GIUOCO, "Продолжение d4 exd4 cxd4 Bb4+ — сильный план для белых.", "d4"),   # a pawn move right after the noun
    ])
    def test_the_lines_first_move_is_proposed(self, fen, sentence, san):
        assert _proposed(fen, sentence) == san

    def test_move_numbers_inside_the_line_do_not_end_it(self):
        assert _proposed(NAJDORF, "Продолжение 6...Nxe4 7.Nxe4 d5 выигрывает фигуру назад.") == "Nxe4"

    def test_the_student_named_as_the_one_who_wins(self):
        assert _proposed(ITAL_D6, "Вариант Nxe5 Nxe5 Qh5 — и ты выигрываешь фигуру.",
                         student_color=chess.WHITE) == "Nxe5"


class TestWhatStaysOutOfTheEngineStage:
    @pytest.mark.parametrize("fen, sentence", [
        # the outcome is told for the other side: a trap shown, not the mover's claim
        (QGD, "Вариант cxd5 exd5 Nxd5 Nxd5 Bxd8 Bb4+ выигрывает чёрным фигуру."),
        (QGD, "Линия cxd5 exd5 Nxd5 — и чёрные выигрывают фигуру."),
        (QGD, "The line cxd5 exd5 Nxd5 Nxd5 Bxd8 Bb4+ wins a piece for Black."),
        # a piece named as the subject after the moves: the outcome is that piece's
        (ITAL_D6, "Вариант Nxe5 dxe5 — пешка нападает на ферзя."),
        # past advice and past praise
        (ITAL_D6, "Лучше был вариант Nxe5 Nxe5 d4 — он выигрывал фигуру."),
        # a doubtful move
        (ITAL_D6, "Линия Nxe5?? Nxe5 Qh5 выигрывает белым фигуру — так не играй."),
        # «линия» as a file, not a line of moves
        (GIUOCO, "По линии f белые давят на пункт f7, это хороший план."),
    ])
    def test_not_proposed(self, fen, sentence):
        assert _proposed(fen, sentence) is None

    def test_the_opponent_named_with_the_student_unknown(self):
        assert _proposed(ITAL_D6, "Вариант Nxe5 Nxe5 Qh5 выигрывает сопернику фигуру.") is None

    def test_the_opponent_is_the_other_side_of_the_student(self):
        assert _proposed(ITAL_D6, "Вариант Nxe5 Nxe5 Qh5 выигрывает сопернику фигуру.", student_color=chess.BLACK) == "Nxe5"
        assert _proposed(ITAL_D6, "Вариант Nxe5 Nxe5 Qh5 выигрывает сопернику фигуру.", student_color=chess.WHITE) is None
        assert _proposed(ITAL_D6, "Линия Nxe5 Nxe5 Qh5 выигрывает противнику фигуру.") is None
        assert _proposed(ITAL_D6, "The line Nxe5 Nxe5 Qh5 wins a piece for the opponent.") is None

    @pytest.mark.parametrize("sentence", [
        "После Bxf7+ Kxf7 Ng5+ Kg8 белые выигрывают пешку.",       # K3: a move told with its reply, unnamed
        "После Bxf7+ чёрные отвечают Kxf7 и выигрывают фигуру.",
    ])
    def test_k3s_reply_rule_is_unchanged_without_a_line_noun(self, sentence):
        assert _proposed(GIUOCO, sentence) is None

    def test_a_named_line_is_still_judged_by_the_sync_check(self):
        ctx = CheckContext.from_fens([QGD])
        assert check_sentence("Вариант cxd5 exd5 Nxd5 выигрывает пешку: конь d5 защищён ферзём.", ctx)
