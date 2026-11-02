"""K3 02.11 (verify1102 VERDICT §6.1): every move of a line is judged on the board where it is played.

Live run 01.11: the engine stage and the board check judged line claims on the board before the reply — «После Qxd4
чёрные отвечают c5 и нападают на ферзя» cut as «Qxd4 is a mistake», «Вот что было лучше: Qxf3» judged as Qf3 on the
board after the game moved on, «e8=N+ … нападает на ферзя g7» judged with the pawn still on e7, a line whose ply was
told in words («4.Nxe5 ферзь идёт на g5: 5.Nxf7 Qxg2») played on a board without that ply. And the forced-reply
check let trap-legal stand 1 run in 3 by the engine's timing. The tests use boards and wordings of their own (the
Philidor, the Scotch, the Two Knights / Traxler, Légal's mate after 4.Nc3 g6, a knight promotion on b8).
"""

import chess
import pytest

from src import hypothetical
from src.answer_check import CheckContext, check_sentence, proposed_move
from src.hypothetical import main_rules, verify_forced_reply, verify_recommendation


def _fen(*sans: str, fen: str = chess.STARTING_FEN) -> str:
    board = chess.Board(fen)
    for san in sans:
        board.push_san(san)
    return board.fen()


PHILIDOR = _fen("e4", "e5", "Nf3", "d6", "d4", "exd4")            # White to move: Nxd4 / Qxd4
SCOTCH = _fen("e4", "e5", "Nf3", "Nc6", "d4", "exd4")
TRAXLER = _fen("e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6", "Ng5", "Bc5")  # Nxf7 hits d8 and h8
TWO_KNIGHTS = _fen("e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6")
LEGAL = _fen("e4", "e5", "Nf3", "d6", "Bc4", "Bg4", "Nc3", "g6")    # 5.Nxe5 Bxd1? 6.Bxf7+ Ke7 7.Nd5#
PROMO = "8/1P1q4/2k5/8/8/8/8/4K3 w - - 0 1"                       # b8=N+ forks c6 and d7
PROMO_ROOK = "7r/1P1q4/2k5/8/8/8/8/4K3 w - - 0 1"


def _ctx(fen: str, question: str = "") -> CheckContext:
    return CheckContext.from_fens([fen], question=question)


def _proposed(fen: str, sentence: str):
    ctx = _ctx(fen)
    assert check_sentence(sentence, ctx) == []
    found = proposed_move(sentence, ctx)
    return found[2] if found else None


# ── the engine stage: what proposed_move hands it ────────────────────────────────────────────────────────────────
class TestThePraiseOfTheReplyIsNoAdvice:
    @pytest.mark.parametrize("fen, sentence", [
        (PHILIDOR, "После Qxd4 чёрные отвечают Nc6 и нападают на ферзя d4."),         # the reply's attack
        (SCOTCH, "После Nxd4 соперник играет Qh4 — и ферзь бьёт пешку e4."),          # the other side plays
        (LEGAL, "После 5.Nxe5 слон забирает ферзя на d1: 6.Bxf7+ Ke7 7.Nd5# — мат."),  # another piece wins
    ])
    def test_a_line_told_with_the_reply_proposes_nothing(self, fen, sentence):
        assert _proposed(fen, sentence) is None

    @pytest.mark.parametrize("sentence", [
        "Nxf7 — и конь бьёт ферзя d8 и ладью h8.",
        "Если конь прыгнет на f7 — он бьёт ферзя d8 и ладью h8.",
    ])
    def test_the_moves_own_praise_is_still_advice(self, sentence):
        assert _proposed(TRAXLER, sentence) == "Nxf7"


class TestAPastBoardsMoveIsNotJudgedNow:
    def test_past_advice_is_not_judged_on_the_board_now(self):
        assert _proposed(TRAXLER, "Лучше было Bxf7+ — слон забирал пешку с шахом.") is None

    def test_the_same_move_told_now_is_judged(self):
        assert _proposed(TRAXLER, "Здесь сильнее Bxf7+ — слон бьёт пешку с шахом.") == "Bxf7+"

    def test_a_capture_that_captures_nothing_here_is_another_boards_move(self):
        # «Bxc6» written with c6 empty: python-chess reads it as Bc6 — not this board's move
        board = chess.Board(_fen("e4", "e5", "Nf3", "d6", "Bb5+", "c6", "Ba4", "Nd7"))
        ctx = CheckContext.from_fens([board.fen()])
        assert proposed_move("Сильнее всего Bb3 — слон уходит из-под удара.", ctx)[2] == "Bb3"
        ctx = CheckContext.from_fens([board.fen()])
        assert proposed_move("Сильнее всего Bxb3 — слон уходит из-под удара.", ctx) is None

    def test_a_pawn_named_with_s_is_no_pawn_move(self):
        fen = _fen("e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "c3", "Nf6")
        assert _proposed(fen, "Сначала разберись с пешкой d4 — она забирает центр.") is None
        assert _proposed(fen, "Сначала пешкой d4 — она забирает центр.") == "d4"


# ── the board check: the board a claim of a line is judged on ────────────────────────────────────────────────────
class TestTheOtherSidesMoveToldInThePresent:
    def test_the_claim_after_it_is_judged_after_it(self):
        assert check_sentence("После Nxd4 чёрные играют c5, и конь на d4 под ударом.", _ctx(PHILIDOR)) == []

    @pytest.mark.parametrize("reply", ["играют a6", "отвечают Nf6"])
    def test_a_reply_that_does_not_attack_is_still_caught(self, reply):
        issues = check_sentence(f"После Nxd4 чёрные {reply}, и конь на d4 под ударом.", _ctx(PHILIDOR))
        assert issues and "nothing attacks White's knight on d4" in issues[0]


class TestAPromotionsPieceIsTheNewOne:
    def test_the_knight_fork_after_the_promotion_is_true(self):
        assert check_sentence("b8=N+ даёт шах и одновременно нападает на ферзя на d7.", _ctx(PROMO)) == []

    def test_the_subject_named_after_the_promotion_is_not_judged_on_the_board_before(self):
        assert check_sentence("Конь на b8 даёт шах королю c6, а заодно нападает на ферзя d7.", _ctx(PROMO)) == []

    def test_a_target_the_new_knight_does_not_reach_is_caught(self):
        issues = check_sentence("b8=N+ даёт шах и одновременно нападает на ладью на h8.", _ctx(PROMO_ROOK))
        assert issues and "not Black's rook on h8" in issues[0]


class TestAPlyToldInWords:
    def test_the_line_goes_on_through_the_ply_told_in_words(self):
        assert check_sentence("После 5.Nxe5 слон бьёт на d1: 6.Bxf7+ Ke7 7.Nd5# — мат.", _ctx(LEGAL)) == []

    def test_a_wrong_mate_on_that_line_is_caught(self):
        assert check_sentence("После 5.Nxe5 слон бьёт на d1: 6.Bxf7+ Ke7 7.Nb5# — мат.", _ctx(LEGAL)) \
            == ["7.Nb5# is not checkmate"]

    def test_a_move_that_line_has_lost_is_caught(self):
        issues = check_sentence("После 5.Nxe5 слон бьёт на d1: 6.Bxf7+ Ke7 7.Qxd1 — и всё.", _ctx(LEGAL))
        assert issues and issues[0].startswith("7.Qxd1 is impossible after the moves before it in this line")

    def test_a_ply_the_words_do_not_tell_leaves_the_line_unjudged(self):
        assert check_sentence("После 5.Nxe5 чёрные ошибаются: 6.Bxf7+ Ke7 7.Nb5# — мат.", _ctx(LEGAL)) == []


class TestAMoveOfALineIsJudgedOnThatLinesBoard:
    def test_a_continuation_that_does_not_fit_the_line_is_not_judged_on_the_board_now(self):
        # «Nf3+» after 3...a6: no knight can go to f3 in that line; on the board now Ng1-f3 is legal and no check
        assert check_sentence("1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 Nf3+ — шах.", _ctx(chess.STARTING_FEN)) == []

    def test_a_wrong_check_on_the_lines_own_board_is_caught(self):
        assert check_sentence("1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.Nc3+ — шах.", _ctx(chess.STARTING_FEN)) \
            == ["5.Nc3+ gives no check"]

    def test_after_a_move_that_fits_no_board_the_check_is_not_judged_on_the_board_now(self):
        # «Bxd1» needs the board after the student's idea, which this turn does not have
        issues = check_sentence("Если чёрные сыграют Bxd1, то Bb5+ — шах.", _ctx(TWO_KNIGHTS))
        assert not any("gives no check" in i for i in issues)
        assert check_sentence("Здесь Bb5+ — шах.", _ctx(TWO_KNIGHTS)) == ["Bb5+ gives no check"]


# ── the engine stage: a verdict that does not depend on the engine's timing ──────────────────────────────────────
def _lines(scores: dict, calls: list):
    """_engine_lines stand-in: scores[fen] → pawns for the side to move (one line, at the depth asked)."""
    def _run(fen, multipv, movetime_ms, depth, deadline=None):
        calls.append(("depth" if depth else "timed", depth))
        if fen not in scores:
            return None
        return {"lines": [{"multipv": 1, "depth": depth or 12, "score": scores[fen], "pv": ""}]}
    return _run


class TestTheRecommendedMoveIsJudgedAtAFixedDepth:
    def _board(self):
        board = chess.Board(SCOTCH)
        move = board.parse_san("Qxd4")
        after = board.copy(stack=False)
        after.push(move)
        return board, move, after

    def test_the_fixed_depth_look_decides_not_a_timed_one(self, monkeypatch):
        board, move, after = self._board()
        calls = []
        # the timed look would call Qxd4 a blunder; the fixed-depth one says it holds
        monkeypatch.setattr("src.hypothetical.analyze_timed", lambda fen, *a, **k: {"lines": [
            {"multipv": 1, "depth": 11, "score": 5.0 if fen == after.fen() else 0.2, "pv": ""}]})
        monkeypatch.setattr("src.hypothetical._engine_lines", _lines({board.fen(): 0.2, after.fen(): -0.1}, calls))
        assert verify_recommendation(board, move, "Qxd4") is None
        assert calls and all(c == ("depth", hypothetical.VERIFY_DEPTH) for c in calls)

    def test_a_loss_at_the_fixed_depth_is_named(self, monkeypatch):
        board, move, after = self._board()
        monkeypatch.setattr("src.hypothetical._engine_lines", _lines({board.fen(): 0.2, after.fen(): 3.0}, []))
        why = verify_recommendation(board, move, "Qxd4")
        assert why and why.startswith("Qxd4 is a mistake on this board (engine)")

    def test_no_fixed_depth_answer_in_time_says_nothing(self, monkeypatch):
        board, move, _ = self._board()
        monkeypatch.setattr("src.hypothetical._engine_lines", lambda *a, **k: None)
        assert verify_recommendation(board, move, "Qxd4") is None

    def test_the_lesson_tutor_keeps_mains_timed_look(self, monkeypatch):
        board, move, after = self._board()
        calls = []
        monkeypatch.setattr("src.hypothetical._engine_lines", _lines({board.fen(): 0.2, after.fen(): -0.1}, calls))
        monkeypatch.setattr("src.hypothetical.analyze_timed", lambda fen, *a, **k: {"lines": [
            {"multipv": 1, "depth": 11, "score": 5.0 if fen == after.fen() else 0.2, "pv": ""}]})
        assert main_rules(verify_recommendation)(board, move, "Qxd4")  # the timed look, as on main
        assert calls == []


class TestTheForcedReplyIsJudgedAtAFixedDepthOnly:
    def test_no_timed_look_is_asked(self, monkeypatch):
        # Two Knights, «после Ng5 чёрные обязаны ответить d5»: judged by the depth search alone
        board = chess.Board(TWO_KNIGHTS)
        board.push_san("Ng5")
        claim = {"board": board, "moves": [board.parse_san("d5")], "named": "d5", "after": "Ng5", "strict": True}
        timed = []
        monkeypatch.setattr("src.hypothetical.analyze_timed", lambda *a, **k: timed.append(a) or {"error": "x"})
        rows_seen = []

        def _rows(b, movetime_ms=None, depth=None, deadline=None):
            rows_seen.append((movetime_ms, depth))
            return [(b.parse_san("d5"), 0.0, None, 0.0), (b.parse_san("Bc5"), -0.2, None, 0.2),
                    (b.parse_san("Nxe4"), -1.0, None, 1.0)]

        monkeypatch.setattr("src.hypothetical._reply_rows", _rows)
        issue = verify_forced_reply(claim, 300, True)
        assert timed == [] and rows_seen == [(None, hypothetical.FORCED_CONFIRM_DEPTH)]
        assert issue and "Bc5 is about as good" in issue
