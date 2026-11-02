"""voice1102: the reason given for castling being impossible is judged against the rule (src/castle_reason.py).

Live 02.11 (voice, the student White, r2qk1nr/ppp3pp/3p4/2b1p3/1nP5/3b1NP1/PP1P1PBP/R1BQK2R w KQkq): «Я не могу сделать
рокировку, потому что поле f2 под боем слона… слон на c5 бьёт поле f2, и по правилам проходить через битое поле при
рокировке нельзя». O-O is illegal there because the bishop d3 hits f1; f2 is not on the king's path. Nothing cut it.

The tests use new boards (kingside and queenside, both colours, after a move, in a game) and new wordings; the positive
cases are also shown to pass with the switch off, so they test the mechanism and not another detector's lucky catch.
"""
from __future__ import annotations

import chess
import pytest
from fastapi.testclient import TestClient

from src import config
from src.answer_check import CheckContext, check_sentence
from src.game_intent import spoken_squares

# ── boards (each checked by python-chess in test_the_boards_are_what_the_cases_say) ─────────────────────────────────
LIVE = "r2qk1nr/ppp3pp/3p4/2b1p3/1nP5/3b1NP1/PP1P1PBP/R1BQK2R w KQkq - 0 9"      # W O-O: f1 hit by Bd3
ITAL = "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"     # W O-O legal; Bc5 hits f2
A6X = "rn1qkbnr/p1pp1ppp/bp6/4p3/4P3/5NP1/PPPP1PBP/RNBQK2R w KQkq - 0 4"         # W O-O: f1 hit by Ba6
KNH3 = "rnbqkb1r/pppp1ppp/8/4p3/2B1P3/5N1n/PPPP1PPP/RNBQK2R w KQkq - 0 5"        # W O-O: g1 hit by Nh3
BLK_A3 = "rnbqk2r/pppp1ppp/5n2/4p3/4P3/B4N2/PPPP1PPP/RN1QKB1R b KQkq - 0 4"       # B O-O: f8 hit by Ba3
BLK_G8 = "rnbqk2r/pppp2pp/5n2/2b1pp2/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 1 4"    # B O-O: g8 hit by Bc4
BLK_C4 = "rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQ1RK1 b kq - 5 4"      # B O-O legal
QS_W = "r3kbnr/ppp1pppp/2nq4/3p1b2/3P1B2/2N5/PPPQPPPP/R3KBNR w KQkq - 6 5"       # W O-O-O legal
QS_W_D = "2kr1bnr/ppp1pppp/2nq4/5b2/3P4/2N5/PP2PPPP/R3KBNR w KQ - 0 8"           # W O-O-O legal, b1 hit by Bf5
QS_B = "r3kbnr/pppqpppp/2n5/3p1b2/3P1B2/2N1P3/PPP2PPP/R2QKBNR b KQkq - 0 5"      # B O-O-O legal
ROOKD = "2r1k2r/pp3ppp/8/8/8/8/PP3PPP/R3K2R w KQk - 0 1"                          # W O-O-O: c1 hit by Rc8; O-O legal
CHECK = "rnbqk1nr/pppp1ppp/8/4p3/1b2P3/3P1N2/PPP2PPP/RNBQKB1R w KQkq - 1 4"       # W in check from Bb4
WIDE = "r3k2r/pppq1ppp/2npbn2/2b1p3/2B1P3/2NPBN2/PPPQ1PPP/R3K2R w KQkq - 4 8"     # all four castlings legal
WIDE_B = WIDE.replace(" w ", " b ")
KNG1 = "rnbqk2r/pppp1ppp/5n2/2b1p3/4P3/5N1P/PPPP1PP1/RNBQKB1R w KQkq - 1 4"       # W O-O blocked by Bf1 only

REASON = "castling reason is wrong"


@pytest.fixture(autouse=True)
def _switch_on(monkeypatch):
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW", raising=False)


def _ctx(fen, student=None, question="", game_moves=None):
    ctx = CheckContext.from_fens([fen], question=question)
    ctx.student_color = student if student is not None else chess.Board(fen).turn
    if game_moves is not None:
        ctx.game_moves = list(game_moves)
    return ctx


def _issues(sentence, fen, voice=False, **kw):
    text = spoken_squares(sentence) if voice else sentence
    return check_sentence(text, _ctx(fen, **kw))


def _reason(issues):
    return [i for i in issues if REASON in i]


def test_the_boards_are_what_the_cases_say():
    from src.board_rules import castling_status

    def st(fen, colour):
        return {w: v[0] for w, v in castling_status(chess.Board(fen), colour).items()}

    assert st(LIVE, chess.WHITE) == {"O-O": False, "O-O-O": False}
    assert chess.Board(LIVE).is_attacked_by(chess.BLACK, chess.F1) and not chess.Board(LIVE).is_attacked_by(chess.BLACK, chess.G1)
    assert st(ITAL, chess.WHITE)["O-O"] and chess.Board(ITAL).is_attacked_by(chess.BLACK, chess.F2)
    assert not st(A6X, chess.WHITE)["O-O"] and chess.Board(A6X).attackers(chess.BLACK, chess.F1) == chess.SquareSet([chess.A6])
    assert chess.Board(KNH3).attackers(chess.BLACK, chess.G1) == chess.SquareSet([chess.H3])
    assert not chess.Board(KNH3).is_attacked_by(chess.BLACK, chess.F1)
    assert chess.Board(BLK_A3).attackers(chess.WHITE, chess.F8) == chess.SquareSet([chess.A3])
    assert chess.Board(BLK_G8).attackers(chess.WHITE, chess.G8) == chess.SquareSet([chess.C4])
    assert st(BLK_C4, chess.BLACK)["O-O"] and st(QS_W, chess.WHITE)["O-O-O"] and st(QS_B, chess.BLACK)["O-O-O"]
    assert st(QS_W_D, chess.WHITE)["O-O-O"] and chess.Board(QS_W_D).is_attacked_by(chess.BLACK, chess.B1)
    assert not st(ROOKD, chess.WHITE)["O-O-O"] and st(ROOKD, chess.WHITE)["O-O"]
    assert chess.Board(CHECK).is_check()
    assert all(st(WIDE, c)[w] for c in (chess.WHITE, chess.BLACK) for w in ("O-O", "O-O-O"))


# ── the live sentences ───────────────────────────────────────────────────────────────────────────────────────────────

LIVE_SENTENCES = [
    "Я не могу сделать рокировку, потому что поле f2 под боем слона…",
    "слон на c5 бьёт поле f2, и по правилам проходить через битое поле при рокировке нельзя.",
    "Я не могу сделать рокировку, потому что поле f2 под боем слона… слон на c5 бьёт поле f2, и по правилам "
    "проходить через битое поле при рокировке нельзя.",
]


@pytest.mark.parametrize("sentence", LIVE_SENTENCES)
@pytest.mark.parametrize("voice", [False, True])
def test_the_live_sentences_are_cut_with_the_true_reason(sentence, voice, monkeypatch):
    issues = _reason(_issues(sentence, LIVE, voice=voice, student=chess.WHITE))
    assert issues and "f2 is not on the king's path" in issues[0], issues
    assert "f1 is attacked by the black bishop on d3" in issues[0]      # the true reason, as board_rules states it
    monkeypatch.setenv("COACH_DETECTORS_OFF", "castle_reason")
    assert _issues(sentence, LIVE, voice=voice, student=chess.WHITE) == []


def test_the_live_answer_through_the_voice_endpoint():
    """/api/coach/voice/check, one sentence at a time with the ones before as «previous» (in words, as transcribed)."""
    client = TestClient(app_())
    said = ["Я не могу сделать рокировку, потому что поле эф два под боем слона…",
            "слон на цэ пять бьёт поле эф два, и по правилам проходить через битое поле при рокировке нельзя."]
    prev = ""
    for text in said:
        r = client.post("/api/coach/voice/check", headers={"X-User-Id": "voice1102-castle"},
                        json={"text": text, "fen": LIVE, "question": "Почему я не могу рокироваться?", "previous": prev})
        assert r.status_code == 200
        assert any("f2 is not on the king's path" in i for i in r.json()["issues"]), r.json()
        prev += text + " "


def app_():
    from src.server import app

    return app


# ── false reasons on new boards ──────────────────────────────────────────────────────────────────────────────────────

FALSE = [
    # a square off the king's path — any board, any colour
    ("Ты не можешь рокироваться, потому что поле f2 под боем слона c5.", ITAL, {}, "f2 is not on the king's path"),
    ("You can't castle because the f2 square is attacked by the bishop on c5.", ITAL, {}, "f2 is not on the king's path"),
    ("Рокировка невозможна: слон c5 бьёт поле f2.", ITAL, {}, "f2 is not on the king's path"),
    ("Чёрные не могут рокироваться, потому что поле f7 под боем слона c4.", BLK_G8, {}, "f7 is not on the king's path"),
    ("Длинная рокировка невозможна, потому что поле b8 под боем.", QS_B, {}, "b8 is not on the king's path"),
    ("Длинная рокировка у тебя невозможна: поле b1 атаковано слоном f5.", QS_W_D, {}, "b1 is not on the king's path"),
    ("Короткая рокировка невозможна, потому что поле d1 под боем ферзя.", ITAL, {}, "d1 is not on the king's path"),
    ("Рокироваться нельзя: король пройдёт через поле e2, а его бьёт конь.", KNG1, {}, "e2 is not on the king's path"),
    ("Если сыграешь h3, рокироваться будет нельзя, потому что поле h2 под боем.", ITAL, {}, "h2 is not on the king's path"),
    ("Слон d3 держит поле f2, и рокироваться ты не сможешь.", LIVE, {}, "f2 is not on the king's path"),
    ("Чёрные не могут рокироваться: поле f1 под боем слона.", BLK_A3, {}, "f1 is not on Black's castling path"),
    # on the path, but nothing attacks it / the named attacker does not
    ("Короткая рокировка невозможна: поле g1 под боем слона a6.", A6X, {}, "nothing of Black's attacks g1"),
    ("Короткая рокировка невозможна: поле f1 под боем коня h3.", KNH3, {}, "nothing of Black's attacks f1"),
    ("Нельзя рокироваться, потому что поле f1 под боем коня.", A6X, {}, "not by a knight"),
    ("Рокировка невозможна: слон на c5 бьёт поле f1.", A6X, {}, "not by the piece on c5"),
    ("Чёрным нельзя рокироваться, потому что поле f8 бьёт слон c4.", BLK_G8, {}, "nothing of White's attacks f8"),
    ("Black cannot castle kingside because f8 is attacked by the bishop on c4.", BLK_G8, {}, "nothing of White's attacks f8"),
    ("Длинная рокировка невозможна: поле d1 под боем ладьи c8.", ROOKD, {}, "nothing of Black's attacks d1"),
    ("Чёрные не могут сделать длинную рокировку, потому что поле c8 атаковано слоном f4.", QS_B, {}, "nothing of White's attacks c8"),
    ("Короткая рокировка тебе недоступна — поле g1 бьёт ферзь d8.", WIDE, {}, "nothing of Black's attacks g1"),
    # a check that is not there
    ("Рокироваться нельзя, потому что король под шахом.", WIDE, {}, "king is not in check"),
    ("Black can't castle because the king is in check.", WIDE_B, {}, "king is not in check"),
    # a piece in the way that is not
    ("Короткая рокировка невозможна, потому что конь на g1 мешает.", ITAL, {}, "g1 is empty"),
    ("Короткой рокировке мешает ферзь d1.", KNG1, {}, "d1 is not between the king and the rook for O-O"),
    ("Длинная рокировка невозможна: между королём и ладьёй стоит слон на c1.", QS_W, {}, "c1 is empty"),
    # a moved king, in a game with its record
    ("Ты не можешь рокироваться, потому что король уже ходил.", ITAL, {"game_moves": ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5"]},
     "have not moved in this game"),
    # after a told move: judged on the board after it
    ("После h3 рокировка всё равно невозможна: поле g1 бьёт слон d3.", LIVE, {}, "nothing of Black's attacks g1"),
    # the king's way named, a square off it; a counterfactual («бы») still names the path
    ("Рокировка невозможна, ведь король пошёл бы через поле f2.", LIVE, {}, "f2 is not on the king's path"),
    ("Нельзя рокироваться через битое поле g1.", LIVE, {}, "nothing of Black's attacks g1"),
    # castling said possible, the path squares named as fine — it is not
    ("Чёрные могут рокироваться коротко: поля f8 и g8 свободны и не под боем.", BLK_A3, {}, "f8 is attacked by the white bishop on a3"),
]


@pytest.mark.parametrize("sentence,fen,kw,want", FALSE)
@pytest.mark.parametrize("voice", [False, True])
def test_a_false_reason_is_cut(sentence, fen, kw, want, voice, monkeypatch):
    issues = _reason(_issues(sentence, fen, voice=voice, **kw))
    assert issues and any(want in i for i in issues), issues
    assert "The truth on this board" in issues[0]
    monkeypatch.setenv("COACH_DETECTORS_OFF", "castle_reason")
    assert not _reason(_issues(sentence, fen, voice=voice, **kw))


# ── true reasons, rule talk, advice, conditions: not cut ─────────────────────────────────────────────────────────────

TRUE = [
    ("Ты не можешь рокироваться, потому что поле f1 под боем слона d3.", LIVE, {}),
    ("Слон d3 бьёт поле f1, поэтому короткая рокировка невозможна.", LIVE, {}),
    ("Короткая рокировка невозможна: король прошёл бы через f1, а его бьёт слон d3.", LIVE, {}),
    ("Short castling is not possible now — f1 is attacked by the black bishop on d3.", LIVE, {}),
    ("Длинная рокировка невозможна: между королём и ладьёй стоят слон c1 и ферзь d1.", LIVE, {}),
    ("Поле f2 под боем слона c5, но рокировке это не мешает — король через f2 не проходит.", ITAL, {}),
    ("Пешка f2 под боем слона c5, а рокироваться нельзя из-за слона d3, который бьёт f1.", LIVE, {}),
    ("Рокировка невозможна не из-за поля f2, а из-за поля f1, которое бьёт слон d3.", LIVE, {}),
    ("По правилам нельзя проходить через битое поле при рокировке.", LIVE, {}),
    ("Нельзя рокироваться через битое поле.", ITAL, {}),
    ("Рокируйся, ведь слон c5 бьёт поле f2 и давит на твоего короля.", ITAL, {}),
    ("Почему нельзя рокироваться — из-за поля f2?", ITAL, {}),
    ("Ты думаешь, что рокироваться нельзя из-за поля f2, но это не так.", ITAL, {}),
    ("Короткая рокировка невозможна: поле g1 бьёт конь h3.", KNH3, {}),
    ("Короткая рокировка невозможна, поле f1 бьёт слон a6.", A6X, {}),
    ("Чёрные не могут рокироваться коротко: поле f8 под боем слона a3.", BLK_A3, {}),
    ("Чёрным нельзя рокироваться, потому что поле g8 бьёт слон c4.", BLK_G8, {}),
    ("Длинная рокировка невозможна: поле c1 под боем ладьи c8.", ROOKD, {}),
    ("Длинная рокировка возможна: поле b1 под боем слона f5, но это не важно — b1 должно быть только пустым.", QS_W_D, {}),
    ("Рокироваться нельзя, потому что король под шахом от слона b4.", CHECK, {}),
    ("Короткая рокировка невозможна, потому что слон на f1 ещё не ушёл.", KNG1, {}),
    ("Рокировка невозможна: король уже ходил.", ITAL, {}),                                 # no game record: unjudged
    ("Ты не можешь рокироваться: король уже ходил.", "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w - - 2 3",
     {"game_moves": ["e4", "e5", "Ke2", "Nc6", "Ke1", "Nb8"]}),
    ("После h3 рокировка всё равно невозможна: поле f1 бьёт слон d3.", LIVE, {}),
    ("Если чёрный конь придёт на h3, рокироваться будет нельзя: поле g1 будет под боем.", ITAL, {}),
    ("Рокировка запрещена в трёх случаях: король под шахом, король проходит через битое поле, король встаёт на битое поле.",
     WIDE, {}),
    ("Black cannot castle queenside: the knight on b8 is in the way.", BLK_C4, {}),
    ("Чёрные могут рокироваться коротко: поля f8 и g8 свободны и не под боем.", BLK_C4, {}),
    ("Рокироваться нельзя: слон d3 бьёт f1 через e2.", LIVE, {}),                         # «через e2» is the bishop's line
    ("Рокироваться нельзя: слон a6 смотрит через d3 и e2 на f1.", A6X, {}),
    ("После рокировки ты не сможешь удержать поле f2 под боем слона c5.", ITAL, {}),        # castling is the time, not the claim
    ("Ты не можешь рокироваться: слон d3 контролирует f1, а слон c5 бьёт f2.", LIVE, {}),
    ("Рокировка невозможна: f1 под боем, а ещё слон c5 давит на f2.", LIVE, {}),
    ("Короткая рокировка невозможна — поле f1 под ударом слона d3; длинная тоже: c1 и d1 заняты.", LIVE, {}),
    ("Ты можешь рокироваться: поле f2 под боем, но король через него не проходит.", ITAL, {}),
    ("One thing that doesn't block castling: the b1 square being attacked during long castling.", QS_W_D, {}),
    ("Рокировка невозможна ни в одну сторону: поле f1 бьёт слон d3, а на ферзевом фланге стоят слон c1 и ферзь d1.", LIVE, {}),
]


@pytest.mark.parametrize("sentence,fen,kw", TRUE)
@pytest.mark.parametrize("voice", [False, True])
def test_a_true_reason_or_no_claim_is_not_cut(sentence, fen, kw, voice):
    assert not _reason(_issues(sentence, fen, voice=voice, **kw))


def test_the_switch_names_the_detector():
    assert config.detector_mode("castle_reason") == "on"
