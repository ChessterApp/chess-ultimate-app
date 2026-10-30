"""A reply claimed forced, judged by the engine (prod check 29.10, fixed 30.10).

«после Nxe5 чёрные обязаны ответить dxe5» (trap-legal): 5...Be6 holds about as well (+2.9 against +2.6 at
depth 24) — dxe5 is the best reply, not a forced one. «Qxd5+. Король вынужден уйти с e6» (mate2-no): Black
takes the queen back, Qxd5. The rules judged forcedness only when the claim could not be true at all (one legal
reply); now the claim is found by the check (src/answer_check_rules.forced_reply_claim) and judged by the engine
in the async stage (src/hypothetical.verify_forced_reply), in the text coach and in voice/check.
"""

import shutil

import chess
import pytest

from src import config, server
from src.answer_check import CheckContext, check_sentence
from src.hypothetical import verify_forced_reply

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
        "После Nxe5 чёрные обязаны ответить Qxd1.",  # not a legal reply there: the check of moves judges it
        "Обычно в таких позициях приходится брать dxe5.",  # a rule in general, no line
        "Чёрные обязаны ответить dxe5.",  # no line, no board: it is White to move here
    ])
    def test_not_a_claim_about_this_line(self, sentence):
        assert _claim(sentence, TRAP) is None

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
        monkeypatch.setattr("src.hypothetical.analyze_timed",
                            _fake({after: [("d6e5", -2.6), ("g4e6", -2.9), ("d6d5", -5.2)]}))
        issue = verify_forced_reply(self._trap_claim(), 300, True)
        assert issue == ("after Nxe5 Black is not forced to play dxe5: Be6 is about as good (+2.9 for White against "
                         "+2.6 for White after dxe5, engine) — it is one good reply, not the only one")

    def test_a_live_game_keeps_the_engines_reply_out(self, monkeypatch):
        after = _after(TRAP, "Nxe5").fen()
        monkeypatch.setattr("src.hypothetical.analyze_timed",
                            _fake({after: [("d6e5", -2.6), ("g4e6", -2.9), ("d6d5", -5.2)]}))
        issue = verify_forced_reply(self._trap_claim(), 300, False)
        assert issue.startswith("after Nxe5 Black is not forced to play dxe5: another reply is about as good")
        assert "Be6" not in issue

    def test_alternatives_much_worse_keep_it_forced(self, monkeypatch):
        # «вынуждены взять, иначе теряют фигуру»: true when everything else is clearly worse.
        after = _after(TRAP, "Nxe5").fen()
        monkeypatch.setattr("src.hypothetical.analyze_timed",
                            _fake({after: [("d6e5", -2.6), ("g4e6", -4.0), ("d6d5", -5.2)]}))
        assert verify_forced_reply(self._trap_claim(), 300, True) is None

    def test_a_gap_near_the_line_is_looked_at_again_deeper(self, monkeypatch):
        after = _after(TRAP, "Nxe5").fen()
        calls = []
        first = _fake({after: [("d6e5", -2.35), ("g4e6", -3.07), ("d6d5", -4.7)]})
        deeper = _fake({after: [("d6e5", -2.43), ("g4e6", -2.9), ("d6d5", -5.2)]})

        def _analyze(fen, movetime_ms, multipv=1, min_depth=10):
            calls.append(movetime_ms)
            return (first if len(calls) == 1 else deeper)(fen, movetime_ms, multipv, min_depth)

        monkeypatch.setattr("src.hypothetical.analyze_timed", _analyze)
        issue = verify_forced_reply(self._trap_claim(), 300, True)
        assert calls == [600, 1200] and issue and "Be6 is about as good" in issue

    def test_the_named_reply_much_worse_than_the_best(self, monkeypatch):
        # mate2-no: the king «must» move, Qxd5 takes the queen back.
        claim = _claim(["Берёшь коня на d5 с шахом: Qxd5+.",
                        "Король вынужден уйти с e6, после чего ты забираешь ферзя, и партия фактически решена."], MATE2)
        after = _after(MATE2, "Qxd5+").fen()
        monkeypatch.setattr("src.hypothetical.analyze_timed",
                            _fake({after: [("d8d5", 6.2), ("e6e7", -5.7), ("e6f5", "mate -4")]}))
        issue = verify_forced_reply(claim, 300, True)
        assert issue == ("after Qxd5+ Black is not forced to make a king move: the best reply is Qxd5 (-6.2 for White "
                         "against +5.7 for White after Ke7, engine) — do not call it forced or the only reply")

    def test_a_named_reply_outside_the_engines_three_is_looked_at_on_its_own(self, monkeypatch):
        claim = _claim("После Nxe5 чёрные обязаны ответить h5.", TRAP)
        board = _after(TRAP, "Nxe5")
        after_h5 = _after(TRAP, "Nxe5", "h5").fen()
        monkeypatch.setattr("src.hypothetical.analyze_timed", _fake({
            board.fen(): [("d6e5", -2.6), ("g4e6", -2.9), ("d6d5", -3.3)], after_h5: [("e5g4", 5.0)]}))
        issue = verify_forced_reply(claim, 300, True)
        assert issue.startswith("after Nxe5 Black is not forced to play h5: the best reply is dxe5 (+2.6 for White "
                                "against +5.0 for White after h5")

    def test_should_is_judged_only_against_the_best(self, monkeypatch):
        claim = _claim("После Nxe5 чёрные должны ответить dxe5.", TRAP)
        after = _after(TRAP, "Nxe5").fen()
        monkeypatch.setattr("src.hypothetical.analyze_timed",
                            _fake({after: [("d6e5", -2.6), ("g4e6", -2.9), ("d6d5", -5.2)]}))
        assert verify_forced_reply(claim, 300, True) is None
        monkeypatch.setattr("src.hypothetical.analyze_timed",
                            _fake({after: [("g4e6", -0.5), ("d6e5", -2.6), ("d6d5", -5.2)]}))
        assert "the best reply is Be6" in verify_forced_reply(claim, 300, True)

    @pytest.mark.parametrize("lines", [
        [("d6e5", "mate -3"), ("g4e6", "mate -3"), ("d6d5", "mate -2")],  # every reply mated the same way: left alone
        [("d6e5", -6.0), ("g4e6", -6.2), ("d6d5", -6.4)],  # a decided position: too coarse to call replies equal
    ])
    def test_mates_and_decided_positions_are_left_alone(self, monkeypatch, lines):
        after = _after(TRAP, "Nxe5").fen()
        monkeypatch.setattr("src.hypothetical.analyze_timed", _fake({after: lines}))
        assert verify_forced_reply(self._trap_claim(), 300, True) is None

    def test_one_legal_reply_needs_no_engine(self, monkeypatch):
        fen = "8/8/8/8/1Nb5/p7/6R1/k1K5 w - - 0 1"
        claim = _claim("Ладья жертвуется под бой: Ra2+ После этого у чёрных только один законный ход — **Сxa2**, "
                       "слон обязан взять ладью.", fen)
        assert claim["named"] == "Bxa2"

        def _boom(*a, **k):
            raise AssertionError("the engine is not asked")

        monkeypatch.setattr("src.hypothetical.analyze_timed", _boom)
        assert verify_forced_reply(claim, 300, True) is None

    def test_the_engine_away_is_not_an_issue(self, monkeypatch):
        monkeypatch.setattr("src.hypothetical.analyze_timed", lambda *a, **k: {"error": "no engine"})
        assert verify_forced_reply(self._trap_claim(), 300, True) is None


@pytest.mark.skipif(not shutil.which("stockfish") and not shutil.which("/opt/homebrew/bin/stockfish"),
                    reason="Stockfish not installed")
class TestWithStockfish:
    """The production positions with the real engine (local Stockfish, no network)."""

    @pytest.fixture(autouse=True)
    def _local_engine(self, monkeypatch):
        monkeypatch.setattr("src.tools.stockfish.ENGINE_API_URL", "", raising=False)

    def test_trap_legal(self):
        issue = verify_forced_reply(_claim(TRAP_SENTENCE, TRAP, TRAP_Q), 300, True)
        assert issue and issue.startswith("after Nxe5 Black is not forced to play dxe5: Be6 is about as good")

    def test_mate2_no(self):
        claim = _claim(["Берёшь коня на d5 с шахом: Qxd5+.",
                        "Король вынужден уйти с e6, после чего ты забираешь ферзя, и партия фактически решена."], MATE2)
        issue = verify_forced_reply(claim, 300, True)
        assert issue and issue.startswith("after Qxd5+ Black is not forced to make a king move: the best reply is Qxd5")

    def test_a_truly_forced_recapture_passes(self):
        claim = _claim("После Nxf7 чёрные обязаны взять Kxf7, иначе теряют ферзя или ладью.", FRIED)
        assert claim and claim["named"] == "Kxf7"
        assert verify_forced_reply(claim, 300, True) is None


class TestWiring:
    """The text coach holds the sentence for the engine; voice/check reads it back (parity)."""

    def test_the_text_coach_does_not_show_it(self, monkeypatch):
        from tests.unit.test_hypothetical import _turn

        after = _after(TRAP, "Nxe5").fen()
        monkeypatch.setattr("src.hypothetical.analyze_timed",
                            _fake({after: [("d6e5", -2.6), ("g4e6", -2.9), ("d6d5", -5.2)]}))
        answer = "Связка тут мнимая. " + TRAP_SENTENCE + " Потом думай о рокировке."
        _, frames = _turn(monkeypatch, answer, TRAP_Q, TRAP, COACH_ANSWER_FIX=False, COACH_HYPOTHETICAL_NOTE=False)
        text = "".join(f.get("delta", "") for f in frames)
        assert "Связка тут мнимая." in text and "рокировке" in text
        assert "обязаны ответить dxe5" not in text

    def test_the_text_coach_shows_a_true_claim(self, monkeypatch):
        from tests.unit.test_hypothetical import _turn

        after = _after(TRAP, "Nxe5").fen()
        monkeypatch.setattr("src.hypothetical.analyze_timed",
                            _fake({after: [("d6e5", -2.6), ("g4e6", -4.4), ("d6d5", -5.2)]}))
        _, frames = _turn(monkeypatch, TRAP_SENTENCE, TRAP_Q, TRAP, COACH_ANSWER_FIX=False, COACH_HYPOTHETICAL_NOTE=False)
        assert "обязаны ответить dxe5" in "".join(f.get("delta", "") for f in frames)

    def test_voice_check_reads_it_back_without_the_engines_move(self, monkeypatch):
        from fastapi.testclient import TestClient

        after = _after(TRAP, "Nxe5").fen()
        monkeypatch.setattr(config, "COACH_MOVE_VERIFY", True)
        monkeypatch.setattr("src.hypothetical.analyze_timed",
                            _fake({after: [("d6e5", -2.6), ("g4e6", -2.9), ("d6d5", -5.2)]}))
        resp = TestClient(server.app).post("/api/coach/voice/check", headers={"X-User-Id": "voice-forced"},
                                           json={"text": "После Nxe5 чёрные обязаны ответить dxe5.", "fen": TRAP})
        issues = resp.json()["issues"]
        assert len(issues) == 1 and issues[0].startswith("after Nxe5 Black is not forced to play dxe5: another reply")
        assert "Be6" not in issues[0]

    def test_voice_check_passes_a_true_claim(self, monkeypatch):
        from fastapi.testclient import TestClient

        after = _after(TRAP, "Nxe5").fen()
        monkeypatch.setattr(config, "COACH_MOVE_VERIFY", True)
        monkeypatch.setattr("src.hypothetical.analyze_timed",
                            _fake({after: [("d6e5", -2.6), ("g4e6", -4.4), ("d6d5", -5.2)]}))
        resp = TestClient(server.app).post("/api/coach/voice/check", headers={"X-User-Id": "voice-forced"},
                                           json={"text": "После Nxe5 чёрные обязаны ответить dxe5.", "fen": TRAP})
        assert resp.json() == {"issues": []}
