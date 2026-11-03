"""voice 03.11: a move said aloud reaches the voice check's engine stage as a written one does.

POST /api/coach/voice/check normalised the sentence (squares said in words → squares, src/game_intent.spoken_squares)
for the board check, but its engine stage read the raw text: «сыграй ферзём на аш четыре» was never verified by the
engine while «сыграй ферзём на h4» was. The student's question was read raw too: the move it named aloud («а если
ферзь жэ четыре?») was not quoted, so the coach's description of the student's own idea was judged as advice.

Now the request is read once (server._voice_heard) and every stage reads that. The tests run the endpoint on boards
and wordings not used by the 02.11 tests, written and said aloud side by side: the engine stage must receive the same
move / forced reply / line for both, and nothing for a sentence with no move (the engine budget does not grow).
"""
from __future__ import annotations

import os
import shutil

import chess
import pytest
from fastapi.testclient import TestClient

from src import config, server

SCOTCH_B = "r1bqkbnr/pppp1ppp/2n5/4p3/3PP3/5N2/PPP2PPP/RNBQKB1R b KQkq d3 0 3"
QGD_W = "rnbqkb1r/ppp2ppp/4pn2/3p4/2PP4/2N5/PP2PPPP/R1BQKBNR w KQkq - 2 4"
LONDON_W = "r2q1rk1/pp2bppp/2n1pn2/3p4/3P1B2/2PB1N2/PP1N1PPP/R2Q1RK1 w - - 4 10"
NAJDORF_W = "rnbqkb1r/1p2pppp/p2p1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 0 6"
CARO_W = "rn1qkbnr/pp2pppp/2p3b1/8/3P4/6N1/PPP2PPP/R1BQKBNR w KQkq - 2 6"
SLAV_B = "rnbqkb1r/pp2pppp/2p2n2/3p4/2PP4/2N2N2/PP2PPPP/R1BQKB1R b KQkq - 3 4"
KID_B = "rnbq1rk1/ppp1ppbp/3p1np1/8/2PPP3/2N2N2/PP2BPPP/R1BQK2R b KQ - 1 6"
ONLY_F3 = "1k2b1r1/8/8/8/8/8/5P1P/7K b - - 0 1"  # after ...Bc6+ White's only legal reply is f3

Q = "Что мне делать?"


@pytest.fixture(autouse=True)
def _engine_stage_on(monkeypatch):
    monkeypatch.setattr(config, "COACH_MOVE_VERIFY", True)
    monkeypatch.setattr(config, "COACH_LINE_VERDICT", True)
    monkeypatch.setattr("src.board_rules.tablebase", lambda board: None)  # no network; no ending on these boards

    async def _no_limit(*a, **k):
        return None

    monkeypatch.setattr(server, "enforce_rate_limit", _no_limit)


@pytest.fixture
def engine_calls(monkeypatch):
    """The engine stage's three verifiers replaced by recorders: what each one was asked, and a fixed verdict."""
    calls = {"move": [], "forced": [], "line": []}

    def _move(board, move, san, *a, **k):
        calls["move"].append(san)
        return f"{san} is a mistake (stub)"

    def _forced(claim, *a, **k):
        calls["forced"].append(claim.get("named") or claim.get("moves"))
        return None

    def _line(claims, *a, **k):
        calls["line"].append([[m.uci() for m in c["moves"]] for c in claims])
        return None

    monkeypatch.setattr("src.hypothetical.verify_recommendation", _move)
    monkeypatch.setattr("src.hypothetical.verify_forced_reply", _forced)
    monkeypatch.setattr("src.line_verdict.verify_claims", _line)
    return calls


def _check(text, fen, question=Q, previous=None):
    body = {"text": text, "fen": fen, "question": question, "engine": True}
    if previous:
        body["previous"] = previous
    resp = TestClient(server.app).post("/api/coach/voice/check", headers={"X-User-Id": "voice-1103"}, json=body)
    assert resp.status_code == 200
    return resp.json()


def test_the_boards_are_what_the_cases_say():
    for fen, san in ((SCOTCH_B, "Qh4"), (QGD_W, "Ne4"), (LONDON_W, "Bg5"), (NAJDORF_W, "Qg4"), (CARO_W, "h4"),
                     (SLAV_B, "Bh3"), (KID_B, "e5")):
        board = chess.Board(fen)
        assert board.is_valid() and board.parse_san(san) in board.legal_moves
    only = chess.Board(ONLY_F3)
    only.push_san("Bc6+")
    assert [only.san(m) for m in only.legal_moves] == ["f3"]


# ── a recommendation said aloud reaches the engine as the written one does ──────────────────────────────────────────
PROPOSALS = [
    # (board, written, said aloud, the move)
    (SCOTCH_B, "Сыграй ферзём на h4.", "Сыграй ферзём на аш четыре.", "Qh4"),
    (QGD_W, "Лучше всего конём на e4.", "Лучше всего конём на е четыре.", "Ne4"),
    (LONDON_W, "Поставь слона на g5.", "Поставь слона на жэ пять.", "Bg5"),
    (NAJDORF_W, "Советую сыграть ферзём на g4.", "Советую сыграть ферзём на жэ четыре.", "Qg4"),
    (CARO_W, "Сыграй пешкой на h4.", "Сыграй пешкой на аш четыре.", "h4"),
    (SLAV_B, "Лучше всего слоном на h3.", "Лучше всего слоном на аш три.", "Bh3"),
    (KID_B, "Поставь пешку на e5.", "Поставь пешку на е пять.", "e5"),
    (QGD_W, "Играй слоном на g5.", "Играй слоном на же пять.", "Bg5"),  # «же» — the transcription's other spelling
]


@pytest.mark.parametrize("fen,written,spoken,san", PROPOSALS)
def test_a_proposal_said_aloud_is_verified_like_the_written_one(engine_calls, fen, written, spoken, san):
    got_written = _check(written, fen)
    asked_written = list(engine_calls["move"])
    engine_calls["move"].clear()
    got_spoken = _check(spoken, fen)
    assert asked_written == [san] and engine_calls["move"] == [san]
    assert got_spoken == got_written == {"issues": [f"{san} is a mistake (stub)"], "engine": True}


def test_a_proposal_said_aloud_after_sentences_said_aloud(engine_calls):
    got = _check("Поэтому сыграй ферзём на жэ четыре.", NAJDORF_W,
                 previous="Слон на цэ восемь ещё не развит. Конь на дэ четыре стоит в центре.")
    assert engine_calls["move"] == ["Qg4"] and got["engine"] is True


NO_MOVE = [
    # nothing proposed: the engine is not asked, whether the squares are written or said
    (SCOTCH_B, "Здесь хорошо пойти ферзём на аш четыре."),  # not a proposal in the written form either
    (SCOTCH_B, "Не играй ферзём на аш четыре — потеряешь темп."),
    (QGD_W, "Слон на цэ восемь пока не развит."),
    (NAJDORF_W, "Конь на эф шесть защищает пешку е четыре? Нет, он на неё нападает."),
    (LONDON_W, "Пешка на дэ четыре держит центр, а слон на эф четыре смотрит на цэ семь."),
    (KID_B, "Чёрные рокировали, король на жэ восемь в безопасности."),
]


@pytest.mark.parametrize("fen,spoken", NO_MOVE)
def test_no_move_said_no_engine(engine_calls, fen, spoken):
    got = _check(spoken, fen)
    assert engine_calls == {"move": [], "forced": [], "line": []}
    assert got["engine"] is False


# ── the student's question said aloud: the move it names is the student's idea, looked at, not advised ──────────────
@pytest.mark.parametrize("question", ["А если ферзь жэ четыре?", "А если ферзём на жэ четыре?", "А если Qg4?"])
def test_the_move_the_question_names_aloud_is_quoted(engine_calls, question):
    got = _check("Играешь Qg4 — и ферзь нападает на слона c8.", NAJDORF_W, question=question)
    assert engine_calls["move"] == [] and got["engine"] is False


def test_the_same_sentence_after_another_question_is_advice(engine_calls):
    got = _check("Играешь Qg4 — и ферзь нападает на слона c8.", NAJDORF_W, question="А если конь бэ три?")
    assert engine_calls["move"] == ["Qg4"] and got["issues"]


def test_the_question_names_aloud_a_move_the_coach_advises_in_so_many_words(engine_calls):
    got = _check("Лучше сыграй ферзём на жэ четыре.", NAJDORF_W, question="А если ферзь жэ четыре?")
    assert engine_calls["move"] == ["Qg4"] and got["issues"]


# ── forced replies and lines said aloud ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("written,spoken,reply", [
    ("После Bc6+ белые обязаны ответить f3.", "После Bc6+ белые обязаны ответить эф три.", "f3"),
    ("После Bc6+ у белых единственный ход — f3.", "После Bc6+ у белых единственный ход — эф три.", "f3"),
])
def test_a_forced_reply_said_aloud(engine_calls, written, spoken, reply):
    _check(written, ONLY_F3)
    asked = list(engine_calls["forced"])
    engine_calls["forced"].clear()
    got = _check(spoken, ONLY_F3)
    assert asked == engine_calls["forced"] and len(asked) == 1 and reply in str(asked[0])
    assert got["engine"] is True


@pytest.mark.parametrize("written,spoken", [
    ("После Nf5 g6 Nh6 белые выигрывают фигуру.", "После Nf5 жэ шесть Nh6 белые выигрывают фигуру."),
    ("После 6.Nf5 g6 7.Nh6 белые теряют коня.", "После 6.Nf5 жэ шесть 7.Nh6 белые теряют коня."),
])
def test_a_line_said_aloud(engine_calls, written, spoken):
    _check(written, NAJDORF_W)
    asked = list(engine_calls["line"])
    engine_calls["line"].clear()
    got = _check(spoken, NAJDORF_W)
    assert asked == engine_calls["line"] == [[["d4f5", "g7g6", "f5h6"]]]
    assert got["engine"] is True


# ── with the real engine ────────────────────────────────────────────────────────────────────────────────────────────
_SF = os.environ.get("STOCKFISH_PATH") or shutil.which("stockfish") or (
    "/opt/homebrew/bin/stockfish" if os.path.exists("/opt/homebrew/bin/stockfish") else None)


@pytest.mark.skipif(_SF is None, reason="the engine stage needs a local Stockfish")
@pytest.mark.parametrize("fen,spoken,bad", [
    (SCOTCH_B, "Сыграй ферзём на аш четыре.", "Qh4"),     # 3...Qh4?? 4.Nxh4
    (KID_B, "Лучше всего слоном на аш шесть.", "Bh6"),   # 6...Bh6?? 7.Bxh6
    (QGD_W, "Сыграй слоном на жэ пять.", None),          # 4.Bg5 — the main line
    (KID_B, "Поставь пешку на е пять.", None),           # 6...e5 — the main line
])
def test_with_the_engine(monkeypatch, fen, spoken, bad):
    monkeypatch.setattr("src.tools.stockfish.ENGINE_API_URL", "")
    got = _check(spoken, fen)
    assert got["engine"] is True
    if bad:
        assert got["issues"] and got["issues"][0].startswith(f"{bad} is a mistake")
    else:
        assert got["issues"] == []
