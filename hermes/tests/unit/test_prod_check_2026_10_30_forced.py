"""A reply claimed forced, judged by the engine (prod check 29.10, fixed 30.10).

«после Nxe5 чёрные обязаны ответить dxe5» (trap-legal): 5...Be6 holds about as well (+2.9 against +2.6 at
depth 24) — dxe5 is the best reply, not a forced one. «Qxd5+. Король вынужден уйти с e6» (mate2-no): Black
takes the queen back, Qxd5. The rules judged forcedness only when the claim could not be true at all (one legal
reply); now the claim is found by the check (src/answer_check_rules.forced_reply_claim) and judged by the engine
in the async stage (src/hypothetical.verify_forced_reply), in the text coach and in voice/check.

Review 30.10: a move of the sentence that continues the line of the sentences before is read there too (a line
only clears, never condemns); a claim denied, called a myth or reported is not the coach's; «X или Y» is a choice;
«ты» is the student; «здесь» after a move told before reads that scene; a verdict is settled at a fixed depth.
"""

import shutil

import chess
import pytest

from src import config, server
from src.answer_check import CheckContext, check_sentence
from src.hypothetical import FORCED_CONFIRM_DEPTH, verify_forced_reply

TRAP = "rn1qkbnr/ppp2p1p/3p2p1/4p3/2B1P1b1/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 0 5"
TRAP_Q = "Можно сейчас сыграть Nxe5? Ведь слон g4 связывает коня."
TRAP_SENTENCE = ("Да, играй — но лови не ферзя, а пешку: после Nxe5 чёрные обязаны ответить dxe5, и тогда спокойно "
                 "берёшь слоном: Qxg4.")
MATE2 = "r1bq1b1r/ppp3pp/2n1k3/3np3/2B5/5Q2/PPPP1PPP/RNB1K2R w KQ - 2 8"
# The Fried Liver after 6.Nxf7: Kxf7 is forced in earnest — anything else loses the queen or the rook.
FRIED = "r1bqkb1r/ppp2ppp/2n5/3np1N1/2B5/8/PPPP1PPP/RNBQK2R w KQkq - 0 6"


def _after(fen: str, *sans: str) -> chess.Board:
    board = chess.Board(fen)
    for san in sans:
        board.push_san(san)
    return board


def _claim(sentences, fen: str, question: str = ""):
    """The forced-reply claim the check recorded for the last of *sentences* (None when none)."""
    ctx = CheckContext.from_fens([fen], question=question)
    sentences = [sentences] if isinstance(sentences, str) else sentences
    for s in sentences:
        issues = check_sentence(s, ctx)
    assert issues == []  # the board itself has nothing against these sentences: only the engine can judge them
    return ctx.forced_claims.get(sentences[-1])


def _fake(lines_by_fen: dict, calls: list = None):
    """analyze_timed stand-in: lines_by_fen[fen] → [(uci, pawns for the side to move | 'mate N'), …] best first."""
    def _analyze(fen, movetime_ms, multipv=1, min_depth=10):
        if calls is not None:
            calls.append((fen, movetime_ms, multipv, min_depth))
        out = []
        for i, (uci, score) in enumerate(lines_by_fen.get(fen, [])[:multipv]):
            line = {"multipv": i + 1, "depth": 16, "pv": uci}
            if isinstance(score, str):
                line["mate_in"] = int(score.split()[1])
                line["score"] = 100.0 if line["mate_in"] > 0 else -100.0
            else:
                line["score"] = score
            out.append(line)
        return {"lines": out} if out else {"error": "no lines"}
    return _analyze


def _engine(monkeypatch, lines_by_fen: dict, deep_by_fen: dict = None, calls: list = None):
    """Both looks of the engine stubbed: the timed one (analyze_timed) and the fixed-depth one that settles a
    verdict (analyze_cached; *deep_by_fen*, the same lines by default)."""
    timed = _fake(lines_by_fen, calls)
    deep = _fake(lines_by_fen if deep_by_fen is None else deep_by_fen)

    def _cached(fen, depth=16, multipv=1):
        if calls is not None:
            calls.append((fen, "depth", depth, multipv))
        res = deep(fen, 0, multipv)
        for line in res.get("lines", []):
            line["depth"] = depth
        return res

    monkeypatch.setattr("src.hypothetical.analyze_timed", timed)
    monkeypatch.setattr("src.hypothetical.analyze_cached", _cached)
    monkeypatch.setattr("src.hypothetical.analyze_position", _cached)


class TestTheClaimIsFound:
    """The check finds the claim, its board and the reply it names; it judges nothing itself."""

    def test_trap_legal_prod_sentence(self):
        claim = _claim(TRAP_SENTENCE, TRAP, TRAP_Q)
        # The student's own Nxe5 (quoted) is the line: the board after it, Black to move.
        assert claim["board"].fen() == _after(TRAP, "Nxe5").fen()
        assert claim["after"] == "Nxe5" and claim["named"] == "dxe5" and claim["strict"] is True

    def test_mate2_no_the_king_must_move_after_the_check_of_the_sentence_before(self):
        claim = _claim(["Берёшь коня на d5 с шахом: Qxd5+.",
                        "Король вынужден уйти с e6, после чего ты забираешь ферзя, и партия фактически решена."], MATE2)
        assert claim["board"].fen() == _after(MATE2, "Qxd5+").fen() and claim["after"] == "Qxd5+"
        assert claim["named"] is None and claim["kind"] == "a king move"
        assert {claim["board"].san(m) for m in claim["moves"]} == {"Ke7", "Kf6", "Kf5"}

    @pytest.mark.parametrize("sentence, named", [
        ("После Nxe5 чёрные вынуждены взять dxe5.", "dxe5"),
        ("После 5.Nxe5 чёрным приходится отвечать 5...dxe5.", "dxe5"),
        ("После Nxe5 у чёрных единственный ответ — dxe5.", "dxe5"),
        ("После Nxe5 у чёрных нет выбора: dxe5.", "dxe5"),
        ("После Nxe5 dxe5 — единственный ход.", "dxe5"),
        ("После Nxe5 чёрные обязаны ответить пешкой dxe5.", "dxe5"),
        ("After Nxe5 Black has to recapture dxe5.", "dxe5"),
        ("После Nxe5 чёрные обязаны ответить слоном: Bxd1.", "Bxd1"),
    ])
    def test_paraphrases(self, sentence, named):
        claim = _claim(sentence, TRAP)
        assert claim is not None and claim["named"] == named and claim["strict"] is True

    def test_should_claims_the_best_reply_not_a_forced_one(self):
        claim = _claim("После Nxe5 чёрные должны ответить dxe5.", TRAP)
        assert claim["named"] == "dxe5" and claim["strict"] is False

    def test_the_named_piece_must_capture(self):
        claim = _claim("После Nxe5 пешка d6 обязана взять коня.", TRAP)
        assert [claim["board"].san(m) for m in claim["moves"]] == ["dxe5"] and claim["kind"] == "a capture"

    @pytest.mark.parametrize("sentence", [
        "Почему после Nxe5 чёрные обязаны ответить dxe5?",  # a question claims nothing
        "После Nxe5 чёрные не обязаны отвечать dxe5.",  # denied
        "Ты думаешь, что после Nxe5 чёрные обязаны ответить dxe5, но это не так.",  # the student's view
        "Если бы после Nxe5 чёрные были обязаны ответить dxe5, связка бы не работала.",  # counterfactual
        "После Nxe5 белые обязаны сыграть d3.",  # the other side's move: another moment of the line
        "Обычно в таких позициях приходится брать dxe5.",  # a rule in general, no line
        "Чёрные обязаны ответить dxe5.",  # no line, no board: it is White to move here
    ])
    def test_not_a_claim_about_this_line(self, sentence):
        assert _claim(sentence, TRAP) is None

    def test_an_impossible_named_reply_is_cut_by_the_move_check(self):
        # «обязаны ответить Qxd1» after Nxe5: the d2 pawn stands between — the scene's move check says so (merge 30.10).
        ctx = CheckContext.from_fens([TRAP])
        issues = check_sentence("После Nxe5 чёрные обязаны ответить Qxd1.", ctx)
        assert issues and "Qxd1 is impossible" in issues[0]

    def test_a_piece_the_side_to_move_lacks_means_the_move_just_written(self):
        # «…Bxb4, слон обязан взять ладью» describes Bxb4 itself; after it White moves and has no bishop.
        fen = "8/1R6/K7/3N4/k7/n7/1P6/2n1b3 w - - 0 1"
        assert _claim("Rb4+, и снова у чёрных один ответ: Bxb4, слон обязан взять ладью.", fen) is None

    def test_a_game_line_from_move_one_is_followed_from_the_start(self):
        # «1.e4 … 4.Bxc6» is the opening told from its first move, not the student's board.
        claim = _claim("После 1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Bxc6 чёрные обязаны взять dxc6.", TRAP)
        assert claim["board"].fen() == _after(chess.STARTING_FEN, "e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Bxc6").fen()
        assert claim["named"] == "dxc6"


class TestTheEngineJudges:
    """verify_forced_reply on a mocked engine: the margins, the mates, the live game."""

    def _trap_claim(self, sentence=TRAP_SENTENCE):
        return _claim(sentence, TRAP, TRAP_Q)

    def test_another_reply_as_good_makes_it_not_forced(self, monkeypatch):
        after = _after(TRAP, "Nxe5").fen()
        _engine(monkeypatch, {after: [("d6e5", -2.6), ("g4e6", -2.9), ("d6d5", -5.2)]})
        issue = verify_forced_reply(self._trap_claim(), 300, True)
        assert issue == ("after Nxe5 Black is not forced to play dxe5: Be6 is about as good (+2.9 for White against "
                         "+2.6 for White after dxe5, engine) — it is one good reply, not the only one")

    def test_a_live_game_keeps_the_engines_reply_out(self, monkeypatch):
        after = _after(TRAP, "Nxe5").fen()
        _engine(monkeypatch, {after: [("d6e5", -2.6), ("g4e6", -2.9), ("d6d5", -5.2)]})
        issue = verify_forced_reply(self._trap_claim(), 300, False)
        assert issue.startswith("after Nxe5 Black is not forced to play dxe5: another reply is about as good")
        assert "Be6" not in issue

    def test_alternatives_much_worse_keep_it_forced(self, monkeypatch):
        # «вынуждены взять, иначе теряют фигуру»: true when everything else is clearly worse.
        after = _after(TRAP, "Nxe5").fen()
        _engine(monkeypatch, {after: [("d6e5", -2.6), ("g4e6", -4.0), ("d6d5", -5.2)]})
        assert verify_forced_reply(self._trap_claim(), 300, True) is None

    def test_the_fixed_depth_look_decides_a_gap_near_the_line(self, monkeypatch):
        # trap-legal at 600 ms: 0.72 (Be6 -3.07 against dxe5 -2.35) one run, 0.69 the next (review 30.10); the
        # search to FORCED_CONFIRM_DEPTH gives the same numbers every time, and they decide.
        after = _after(TRAP, "Nxe5").fen()
        calls = []
        _engine(monkeypatch, {after: [("d6e5", -2.35), ("g4e6", -3.07), ("d6d5", -4.7)]},
                {after: [("d6e5", -2.44), ("g4e6", -2.94), ("d6d5", -5.0)]}, calls)
        issue = verify_forced_reply(self._trap_claim(), 300, True)
        assert [c[1] for c in calls] == [600, "depth"] and calls[1][2] == FORCED_CONFIRM_DEPTH
        assert issue and "Be6 is about as good (+2.9 for White against +2.4 for White after dxe5" in issue

    def test_a_timed_verdict_against_the_claim_is_not_final(self, monkeypatch):
        # The timed look calls Be6 as good; the fixed-depth one does not: the claim stands.
        after = _after(TRAP, "Nxe5").fen()
        _engine(monkeypatch, {after: [("d6e5", -2.4), ("g4e6", -2.7), ("d6d5", -4.7)]},
                {after: [("d6e5", -2.4), ("g4e6", -3.6), ("d6d5", -5.0)]})
        assert verify_forced_reply(self._trap_claim(), 300, True) is None

    def test_a_claim_far_from_the_lines_needs_no_deep_look(self, monkeypatch):
        after = _after(TRAP, "Nxe5").fen()
        calls = []
        _engine(monkeypatch, {after: [("d6e5", -2.4), ("g4e6", -4.6), ("d6d5", -5.0)]}, calls=calls)
        assert verify_forced_reply(self._trap_claim(), 300, True) is None
        assert [c[1] for c in calls] == [600]

    def test_a_deep_look_short_of_its_depth_says_nothing(self, monkeypatch):
        # A loaded host stops the search early: no verdict rather than one that flips with the load.
        after = _after(TRAP, "Nxe5").fen()
        _engine(monkeypatch, {after: [("d6e5", -2.6), ("g4e6", -2.9), ("d6d5", -5.2)]})
        shallow = _fake({after: [("d6e5", -2.6), ("g4e6", -2.9), ("d6d5", -5.2)]})
        monkeypatch.setattr("src.hypothetical.analyze_cached", lambda fen, depth=16, multipv=1: shallow(fen, 0, multipv))
        monkeypatch.setattr("src.hypothetical.analyze_position", lambda fen, depth=16, multipv=1: shallow(fen, 0, multipv))
        assert verify_forced_reply(self._trap_claim(), 300, True) is None

    def test_the_named_reply_much_worse_than_the_best(self, monkeypatch):
        # mate2-no: the king «must» move, Qxd5 takes the queen back.
        claim = _claim(["Берёшь коня на d5 с шахом: Qxd5+.",
                        "Король вынужден уйти с e6, после чего ты забираешь ферзя, и партия фактически решена."], MATE2)
        after = _after(MATE2, "Qxd5+").fen()
        _engine(monkeypatch, {after: [("d8d5", 6.2), ("e6e7", -5.7), ("e6f5", "mate -4")]})
        issue = verify_forced_reply(claim, 300, True)
        assert issue == ("after Qxd5+ Black is not forced to make a king move: the best reply is Qxd5 (-6.2 for White "
                         "against +5.7 for White after Ke7, engine) — do not call it forced or the only reply")

    def test_a_named_reply_outside_the_engines_three_is_looked_at_on_its_own(self, monkeypatch):
        claim = _claim("После Nxe5 чёрные обязаны ответить h5.", TRAP)
        board = _after(TRAP, "Nxe5")
        after_h5 = _after(TRAP, "Nxe5", "h5").fen()
        _engine(monkeypatch, {
            board.fen(): [("d6e5", -2.6), ("g4e6", -2.9), ("d6d5", -3.3)], after_h5: [("e5g4", 5.0)]})
        issue = verify_forced_reply(claim, 300, True)
        assert issue.startswith("after Nxe5 Black is not forced to play h5: the best reply is dxe5 (+2.6 for White "
                                "against +5.0 for White after h5")

    def test_should_is_judged_only_against_the_best(self, monkeypatch):
        claim = _claim("После Nxe5 чёрные должны ответить dxe5.", TRAP)
        after = _after(TRAP, "Nxe5").fen()
        _engine(monkeypatch, {after: [("d6e5", -2.6), ("g4e6", -2.9), ("d6d5", -5.2)]})
        assert verify_forced_reply(claim, 300, True) is None
        _engine(monkeypatch, {after: [("g4e6", -0.5), ("d6e5", -2.6), ("d6d5", -5.2)]})
        assert "the best reply is Be6" in verify_forced_reply(claim, 300, True)

    @pytest.mark.parametrize("lines", [
        [("d6e5", "mate -3"), ("g4e6", "mate -3"), ("d6d5", "mate -2")],  # every reply mated the same way: left alone
        [("d6e5", -6.0), ("g4e6", -6.2), ("d6d5", -6.4)],  # a decided position: too coarse to call replies equal
    ])
    def test_mates_and_decided_positions_are_left_alone(self, monkeypatch, lines):
        after = _after(TRAP, "Nxe5").fen()
        _engine(monkeypatch, {after: lines})
        assert verify_forced_reply(self._trap_claim(), 300, True) is None

    def test_one_legal_reply_needs_no_engine(self, monkeypatch):
        fen = "8/8/8/8/1Nb5/p7/6R1/k1K5 w - - 0 1"
        claim = _claim("Ладья жертвуется под бой: Ra2+ После этого у чёрных только один законный ход — **Сxa2**, "
                       "слон обязан взять ладью.", fen)
        assert claim["named"] == "Bxa2"

        def _boom(*a, **k):
            raise AssertionError("the engine is not asked")

        monkeypatch.setattr("src.hypothetical.analyze_timed", _boom)
        monkeypatch.setattr("src.hypothetical.analyze_cached", _boom)
        monkeypatch.setattr("src.hypothetical.analyze_position", _boom)
        assert verify_forced_reply(claim, 300, True) is None

    def test_the_engine_away_is_not_an_issue(self, monkeypatch):
        monkeypatch.setattr("src.hypothetical.analyze_timed", lambda *a, **k: {"error": "no engine"})
        monkeypatch.setattr("src.hypothetical.analyze_cached", lambda *a, **k: {"error": "no engine"})
        monkeypatch.setattr("src.hypothetical.analyze_position", lambda *a, **k: {"error": "no engine"})
        assert verify_forced_reply(self._trap_claim(), 300, True) is None


# The puzzle «Мат в 3 хода — Набор 13» (prod programme 19.10 and 23.10) and the retry set's «Смешанные — Набор 12».
MATE3 = "2r1kb1r/1b3pp1/p3N2p/1p2P3/5P1B/2PBq2P/P5PK/3R1R2 w - - 0 1"
MATE3_ANSWER = ["Первый ход — **Bxb5+**, с шахом бьём пешку на b5.",
                "Смысл в жертве: чёрные вынуждены ответить **axb5**, забирая слона.",
                "Дальше **Nc7+** — конь с шахом встаёт на c7, и чёрные обязаны ответить **Rxc7**: это единственный ход."]
RETRY12 = "1r2kb2/2qb1p2/p2pp1p1/6Br/1n1QPP1P/2N5/1PPN2R1/2KR4 b - - 0 1"
# After 1.e4 e5 2.d4 exd4 3.Qxd4 Nc6: Qe3, Qa4, Qc4 are about equal.
CG = "r1bqkbnr/pppp1ppp/2n5/8/3QP3/8/PPP2PPP/RNB1KBNR w KQkq - 1 4"


def _readings(claim) -> list:
    return [claim["board"].fen()] + [c["board"].fen() for c in claim["also"]]


class TestTheLineOfTheSentencesBefore:
    """A move of this sentence legal on the screen board too may continue the line the sentences before wrote
    (review 30.10: Rxc7, Kb1, Ke7 — each the only legal reply in its line — were cut as «not forced»)."""

    def test_the_line_continued_is_a_reading_and_clears_it(self, monkeypatch):
        claim = _claim(MATE3_ANSWER, MATE3)
        line = _after(MATE3, "Bxb5+", "axb5", "Nc7+")
        assert [line.san(m) for m in line.legal_moves] == ["Rxc7"]
        assert _readings(claim) == [_after(MATE3, "Nc7+").fen(), line.fen()]
        # On the screen board Kd7 is the better reply; in the line Rxc7 is the only one: the claim stands.
        _engine(monkeypatch, {_after(MATE3, "Nc7+").fen(): [("e8d7", -2.1), ("c8c7", "mate -2")]})
        assert verify_forced_reply(claim, 300, True) is None

    def test_wrong_in_every_reading_the_lines_own_speaks(self, monkeypatch):
        claim = _claim(MATE3_ANSWER, MATE3)
        screen, line = _readings(claim)
        _engine(monkeypatch, {screen: [("e8d7", -2.1), ("c8c7", "mate -2")]})
        claim["also"][0]["moves"] = list(claim["also"][0]["board"].legal_moves)[:1]
        assert verify_forced_reply(claim, 300, True) is None  # one legal reply there: forced by the rules

    def test_the_retry_line_kb1_is_the_only_reply(self):
        claim = _claim(["Ход чёрных — Qxc3!",
                        "Дальше белые вынуждены играть Nc4 — конь d2 встаёт на c4, чтобы прикрыть поле c2 и защитить ферзя d4.",
                        "Но ты не отступаешь: Na2+ — шах, и у белых единственный ответ Kb1."], RETRY12)
        line = _after(RETRY12, "Qxc3", "Nc4", "Na2+")
        assert [line.san(m) for m in line.legal_moves] == ["Kb1"]
        assert line.fen() in _readings(claim)
        assert verify_forced_reply(claim, 300, True) is None  # no engine needed: in the line Kb1 is forced

    def test_the_students_quoted_move_continues_the_line_too(self):
        # «после Nxe5 Bxd1 белые дают шах слоном. На Bxf7+ король обязан ответить Ke7» — Légal's mate: the quoted
        # Nxe5 is not a scene of the other checks, but it is the line here.
        claim = _claim(["Да, это знаменитая ловушка Легаля: после Nxe5 Bxd1 белые дают шах слоном.",
                        "На Bxf7+ король обязан ответить Ke7, а затем конь с c3 даёт мат на d5."], TRAP, TRAP_Q)
        assert _after(TRAP, "Nxe5", "Bxd1", "Bxf7+").fen() in _readings(claim)
        assert verify_forced_reply(claim, 300, True) is None

    def test_a_line_alone_never_condemns(self):
        # Only the line makes the moves legal: a derived board clears, it does not condemn by itself.
        assert _claim(["Если чёрные возьмут ферзя: Nxe5 Bxd1.", "Король обязан идти Ke7 после Bxf7+."], TRAP, TRAP_Q) is None


class TestHereAfterAMoveToldBefore:
    """«здесь / сейчас» after a move of the sentence before (review 30.10: «Rh8+. Здесь король вынужден уйти с e8»
    was judged with White to move)."""

    ROOK = "1r2k3/8/8/8/8/8/8/R3K2R w KQ - 0 1"

    def test_the_scene_is_read_and_the_kings_square_must_be_the_side_to_moves(self):
        claim = _claim(["Ладья даёт шах: Rh8+.", "Здесь король вынужден уйти с e8, и ты забираешь ладью b8."], self.ROOK)
        assert _readings(claim) == [_after(self.ROOK, "Rh8+").fen()]
        assert verify_forced_reply(claim, 300, True) is None  # every legal reply is a king move

    def test_mate2_no_with_here(self):
        claim = _claim(["Берёшь коня на d5 с шахом: Qxd5+.", "Здесь король вынужден уйти с e6."], MATE2)
        assert _readings(claim) == [_after(MATE2, "Qxd5+").fen()]

    @pytest.mark.parametrize("sentence", [
        "Здесь король вынужден уйти с e8.",  # the white king is on e1
        "Здесь король вынужден уйти.",  # not in check: a moment told before (one sentence of voice/check)
    ])
    def test_the_board_as_it_is_does_not_fit(self, sentence):
        assert _claim(sentence, self.ROOK) is None


class TestTheClaimDisowned:
    """A claim the sentence denies, calls a myth or reports as someone's is not the coach's (review 30.10)."""

    @pytest.mark.parametrize("sentence", [
        "Неверно, что после Nxe5 чёрные обязаны ответить dxe5: есть ещё Be6.",
        "Часто пишут, что после Nxe5 чёрные обязаны ответить dxe5, но это не так.",
        "Это не значит, что после Nxe5 чёрные обязаны ответить dxe5.",
        "Многие новички считают, что после Nxe5 чёрные обязаны ответить dxe5.",
        "Распространённый миф: после Nxe5 чёрные обязаны ответить dxe5.",
        "Кстати, после Nxe5 чёрные обязаны ответить dxe5 — это заблуждение, Be6 ничуть не хуже.",
        "Не совсем верно говорить, что после Nxe5 чёрным приходится брать dxe5.",
        "Неправда, будто после Nxe5 у чёрных единственный ответ — dxe5.",
        "It is not true that after Nxe5 Black must play dxe5: Be6 also holds.",
        "It is a myth that after Nxe5 Black must play dxe5.",
    ])
    def test_trap(self, sentence):
        assert _claim(sentence, TRAP) is None

    @pytest.mark.parametrize("sentence", [
        "Неверно, что сейчас белые обязаны сыграть Qe3: Qa4 и Qc4 ничуть не хуже.",
        "Это вовсе не значит, что сейчас ферзь обязан отступить: Qe3 — у тебя есть и Qa4.",
        "Нет: сказать, что сейчас у белых единственный ход — Qe3, нельзя, Qa4 и Qc4 так же хороши.",
    ])
    def test_center_game(self, sentence):
        assert _claim(sentence, CG) is None

    def test_the_rewrite_of_mate2_no_is_not_cut(self):
        assert _claim(["Берёшь коня на d5 с шахом: Qxd5+.",
                       "Ошибочно думать, что король вынужден уйти с e6 — чёрные просто берут ферзя Qxd5."], MATE2) is None


class TestAChoiceOfReplies:
    """«dxe5 или Be6», "Qe3 or Qa4": a set of replies, not one forced (review 30.10)."""

    @pytest.mark.parametrize("sentence, fen", [
        ("После Nxe5 чёрным придётся ответить dxe5 или Be6 — в обоих случаях пешка потеряна.", TRAP),
        ("After Nxe5 Black has to play dxe5 or Be6, and either way a pawn is lost.", TRAP),
        ("Сейчас ферзю придётся отступить: Qe3 или Qa4 — выбирай любой.", CG),
        ("Right now the queen has to retreat: Qe3 or Qa4, both are fine.", CG),
        ("Сейчас ферзь атакован, и тебе придётся отступить: Qe3 или Qa4, оба хода нормальные.", CG),
        ("Сейчас у белых единственный ход — Qe3, Qa4 или Qc4.", CG),
    ])
    def test_listed(self, sentence, fen):
        assert _claim(sentence, fen) is None

    def test_a_move_away_with_an_example_claims_every_move_of_the_piece(self, monkeypatch):
        claim = _claim("Сейчас ферзь атакован, и тебе придётся отступить: Qe3.", CG)
        board = chess.Board(CG)
        assert claim["named"] is None and claim["kind"] == "a queen move"
        assert set(claim["moves"]) == {m for m in board.legal_moves if m.from_square == chess.D4}
        _engine(monkeypatch, {CG: [("d4e3", -0.2), ("d4a4", -0.2), ("d4c4", -0.3)]})
        assert verify_forced_reply(claim, 300, True) is None


class TestYouIsTheStudent:
    """«ты / вы» in the claim's clause is the student (the side to move when unknown), not the side the clause
    before named (review 30.10)."""

    def test_the_comments_own_example(self):
        fen = "8/8/8/P4k2/8/8/8/7K b - - 0 1"
        claim = _claim("Смотри: после Ke5 белые играют a6, и ты обязан идти Kd6 — иначе пешка просто идёт в ферзи.", fen)
        assert claim["board"].fen() == _after(fen, "Ke5", "a6").fen() and claim["named"] == "Kd6"

    def test_the_white_side_named_before(self):
        fen = _after(TRAP, "Nxe5").fen()
        claim = _claim("Белые взяли пешку, а ты обязан ответить dxe5.", fen)
        assert claim["board"].fen() == fen and claim["named"] == "dxe5"

    def test_a_student_of_the_other_side(self):
        fen = _after(TRAP, "Nxe5").fen()
        ctx = CheckContext.from_fens([fen])
        ctx.student_color = chess.WHITE
        assert check_sentence("Белые взяли пешку, а ты обязан ответить dxe5.", ctx) == []
        assert not ctx.forced_claims


@pytest.mark.skipif(not shutil.which("stockfish") and not shutil.which("/opt/homebrew/bin/stockfish"),
                    reason="Stockfish not installed")
class TestWithStockfish:
    """The production positions with the real engine (local Stockfish, no network)."""

    @pytest.fixture(autouse=True)
    def _local_engine(self, monkeypatch):
        monkeypatch.setattr("src.tools.stockfish.ENGINE_API_URL", "", raising=False)
        # No time cap on the fixed-depth search: a loaded test host would stop it short, and then the engine says
        # nothing (test_a_deep_look_short_of_its_depth_says_nothing) — the numbers here are the depth's own.
        monkeypatch.setattr("src.tools.stockfish.MAX_MS", 0, raising=False)

    def test_trap_legal(self):
        issue = verify_forced_reply(_claim(TRAP_SENTENCE, TRAP, TRAP_Q), 300, True)
        assert issue and issue.startswith("after Nxe5 Black is not forced to play dxe5: Be6 is about as good")

    def test_mate2_no(self):
        claim = _claim(["Берёшь коня на d5 с шахом: Qxd5+.",
                        "Король вынужден уйти с e6, после чего ты забираешь ферзя, и партия фактически решена."], MATE2)
        issue = verify_forced_reply(claim, 300, True)
        assert issue and issue.startswith("after Qxd5+ Black is not forced to make a king move: the best reply is Qxd5")

    def test_the_puzzle_line_passes(self):
        assert verify_forced_reply(_claim(MATE3_ANSWER, MATE3), 300, True) is None

    def test_a_truly_forced_recapture_passes(self):
        claim = _claim("После Nxf7 чёрные обязаны взять Kxf7, иначе теряют ферзя или ладью.", FRIED)
        assert claim and claim["named"] == "Kxf7"
        assert verify_forced_reply(claim, 300, True) is None


class TestWiring:
    """The text coach holds the sentence for the engine; voice/check reads it back (parity)."""

    def test_the_text_coach_does_not_show_it(self, monkeypatch):
        from tests.unit.test_hypothetical import _turn

        after = _after(TRAP, "Nxe5").fen()
        _engine(monkeypatch, {after: [("d6e5", -2.6), ("g4e6", -2.9), ("d6d5", -5.2)]})
        answer = "Связка тут мнимая. " + TRAP_SENTENCE + " Потом думай о рокировке."
        _, frames = _turn(monkeypatch, answer, TRAP_Q, TRAP, COACH_ANSWER_FIX=False, COACH_HYPOTHETICAL_NOTE=False)
        text = "".join(f.get("delta", "") for f in frames)
        assert "Связка тут мнимая." in text and "рокировке" in text
        assert "обязаны ответить dxe5" not in text

    def test_the_text_coach_shows_a_true_claim(self, monkeypatch):
        from tests.unit.test_hypothetical import _turn

        after = _after(TRAP, "Nxe5").fen()
        _engine(monkeypatch, {after: [("d6e5", -2.6), ("g4e6", -4.4), ("d6d5", -5.2)]})
        _, frames = _turn(monkeypatch, TRAP_SENTENCE, TRAP_Q, TRAP, COACH_ANSWER_FIX=False, COACH_HYPOTHETICAL_NOTE=False)
        assert "обязаны ответить dxe5" in "".join(f.get("delta", "") for f in frames)

    def test_voice_check_reads_it_back_without_the_engines_move(self, monkeypatch):
        from fastapi.testclient import TestClient

        after = _after(TRAP, "Nxe5").fen()
        monkeypatch.setattr(config, "COACH_MOVE_VERIFY", True)
        _engine(monkeypatch, {after: [("d6e5", -2.6), ("g4e6", -2.9), ("d6d5", -5.2)]})
        resp = TestClient(server.app).post("/api/coach/voice/check", headers={"X-User-Id": "voice-forced"},
                                           json={"text": "После Nxe5 чёрные обязаны ответить dxe5.", "fen": TRAP})
        issues = resp.json()["issues"]
        assert len(issues) == 1 and issues[0].startswith("after Nxe5 Black is not forced to play dxe5: another reply")
        assert "Be6" not in issues[0]

    def test_voice_check_passes_a_true_claim(self, monkeypatch):
        from fastapi.testclient import TestClient

        after = _after(TRAP, "Nxe5").fen()
        monkeypatch.setattr(config, "COACH_MOVE_VERIFY", True)
        _engine(monkeypatch, {after: [("d6e5", -2.6), ("g4e6", -4.4), ("d6d5", -5.2)]})
        resp = TestClient(server.app).post("/api/coach/voice/check", headers={"X-User-Id": "voice-forced"},
                                           json={"text": "После Nxe5 чёрные обязаны ответить dxe5.", "fen": TRAP})
        assert resp.json() == {"issues": []}
