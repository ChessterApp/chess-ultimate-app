"""fix1101 integration (01.11): what the merge of F1–F8 and their cross-package patches needed on top.

  placement   a piece carrying its own square («слон на c1», «слон e8»), or «на <square>» right after a piece noun
              («ладьёй на a1»), is no placement claim on that square (two corpus sentences were read so in shadow)
  gave_up     a sacrifice «still on offer» needs a capture that wins material by exchange (after 6...Kxf7 in the Fried
              Liver, Bxd5+ Qxd5 is an even trade: «Чёрные отдали коня» is judged)
  proposals   a move the sentence says is stopped is no advice (F3's prevention frame in proposed_move), outside /learn
  shadow      record_shadow with no check to land on still logs; with one it lands on the check
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import chess
import pytest

from src import config
from src.answer_check import CheckContext, check_sentence, record_shadow, shadow_into

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
from ctx_fixture import run_answer  # noqa: E402

FRIED = "e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5 Nxf7 Kxf7"
D1_LONG = "r2qk2r/ppp2ppp/2np1n2/4p3/2b1P3/2N2N2/PPP2PPP/R1BQK2R w KQkq - 0 8"


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    monkeypatch.setattr(config, "STOCKFISH_POOL", False, raising=False)
    monkeypatch.setattr(config, "COACH_PRECOMPUTE", False, raising=False)
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW", raising=False)


def _board_ctx(fen: str) -> CheckContext:
    ctx = CheckContext.from_fens([fen], [])
    ctx.language = "ru"
    return ctx


def _game_ctx(moves: str, student=chess.WHITE) -> CheckContext:
    b = chess.Board()
    for san in moves.split():
        b.push_san(san)
    ctx = CheckContext.from_fens([b.fen()], [], student_color=student)
    ctx.game_moves = moves.split()
    first = 0 if student == chess.BLACK else 1
    ctx.game_engine_moves = [m for i, m in enumerate(moves.split()) if i % 2 == first]
    ctx.language = "ru"
    return ctx


# ── placement ─────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "Между королём и ладьёй на a1 стоят свои слон на c1 и ферзь на d1 — их надо сначала развести.",
    "У короля на e1 стоит рядом ферзь.",
    "На a8 стоит чёрный слон e8, который прикрывает поле.",
    "На b1 стоит конь на c3.",
])
def test_a_square_of_another_noun_is_no_placement(monkeypatch, sentence):
    monkeypatch.setitem(config.DETECTOR_DEFAULTS, "placement", "on")
    assert run_answer([sentence], _board_ctx(D1_LONG))[-1][1] == []


@pytest.mark.parametrize("sentence,issue", [
    ("На a1 стоит белый слон.", "on a1 stands White's rook, not a bishop"),
    ("Белый ферзь стоит на e2.", "e2 is empty"),
    ("На c1 стоит белый конь.", "on c1 stands White's bishop, not a knight"),
])
def test_a_plain_placement_is_still_judged(monkeypatch, sentence, issue):
    monkeypatch.setitem(config.DETECTOR_DEFAULTS, "placement", "on")
    assert any(issue in i for i in run_answer([sentence], _board_ctx(D1_LONG))[-1][1])


# ── gave_up: a sacrifice on offer must win material ───────────────────────────────────────────────────────────────
def test_an_even_trade_is_no_sacrifice_on_offer():
    issues = check_sentence("Чёрные отдали коня.", _game_ctx(FRIED))
    assert any("has lost no knight" in i for i in issues)


def test_a_sacrifice_still_on_offer_is_not_judged():
    # 2.f4: exf4 wins a pawn — the gambit pawn is offered, not yet lost
    assert check_sentence("Белые пожертвовали пешку.", _game_ctx("e4 e5 f4")) == []


def test_true_losses_pass():
    assert check_sentence("Ты отдал коня за пешку.", _game_ctx(FRIED)) == []
    assert check_sentence("Чёрные отдали пешку f7.", _game_ctx(FRIED)) == []


# ── proposals: the stopped move is no advice ──────────────────────────────────────────────────────────────────────
def test_a_stopped_move_is_no_proposal():
    from src.answer_check import _proposed_move

    b = chess.Board()
    for san in "e4 c6 Nf3".split():
        b.push_san(san)
    ctx = CheckContext.from_fens([b.fen()], ["e4 c6 Nf3"])
    ctx.language = "ru"
    got = _proposed_move("Лучше d5, не давая белым спокойно сыграть d4.", ctx)
    assert got is not None and got[2] == "d5"
    b2 = chess.Board()
    for san in "e4 c6".split():
        b2.push_san(san)
    ctx2 = CheckContext.from_fens([b2.fen()], ["e4 c6"])
    ctx2.language = "ru"
    got2 = _proposed_move("Стоит, не давая чёрным сыграть d5.", ctx2)
    assert got2 is None or got2[2] != "d5"


# ── shadow ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_shadow_without_a_check_is_logged(caplog):
    with caplog.at_level(logging.INFO, logger="src.answer_check"):
        record_shadow(None, "trades", ["an issue"], "a sentence")
    assert any("detector trades (shadow)" in r.getMessage() for r in caplog.records)


def test_shadow_inside_a_check_lands_on_it():
    ctx = CheckContext.from_fens()
    with shadow_into(ctx, "a sentence"):
        record_shadow(None, "piece_decides", ["an issue"])
    assert ctx.detector_shadow == [("piece_decides", "a sentence", ["an issue"])]
