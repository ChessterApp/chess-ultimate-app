"""WP-0 of plan 31.10 (detect-1031): the shared foundation every package builds on.

game_record (the game's own record), board_math (the shared static exchange), the claim types' additions, the
turn facts, the detector switches, the hooks in files other packages own (trade_issues, rules_block's board
verdicts, stockfish's searchmoves, /health's book_index_ready) — each with its stub behaving as main did.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import chess
import pytest

from src import board_math, config, game_record
from src.answer_check import CheckContext, check_sentence
from src.claim_types import (ALL_RELATIONS, OTHER_RELATIONS, PRESUPS, RELATIONS, RULE_RELATIONS, Claim, Pos, Ref,
                             UNDECIDED)

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "detect1031"


def _wc6_moves():
    from src.famous_games import GAMES, _replay

    g = next(g for g in GAMES if g["key"] == "wch2021-g6")
    return g, _replay(g)[1]


def _game(sans: str, color=None) -> CheckContext:
    moves = sans.split()
    b = chess.Board()
    for m in moves:
        b.push_san(m)
    ctx = CheckContext.from_fens([b.fen()], student_color=color)
    ctx.game_moves = moves
    return ctx


# ── game_record ──────────────────────────────────────────────────────────────────────────────────────────────────
ST4 = "e4 e5 d4 d6 c3 Be7 Nf3 Nf6 Bc4 exd4 O-O Nxe4"


def test_recap_of_the_whole_game_ends_now():
    ctx = _game(ST4)
    assert game_record.recap_end(ctx, "Позиция после 1.e4 e5 2.d4 d6 3.c3 Be7 4.Nf3 Nf6 5.Bc4 exd4 6.O-O Nxe4:") == 12


def test_recap_that_ends_early_is_not_now():
    ctx = _game(ST4)
    assert game_record.recap_end(ctx, "после 1.e4 e5 2.d4 d6 3.c3 Be7 4.Nf3 Nf6 5.Bc4 exd4") == 10


def test_invented_line_is_no_recap():
    ctx = _game(ST4)
    assert game_record.recap_end(ctx, "после 1.e4 e5 2.Nf3 Nc6 у белых лишняя пешка") is None
    assert game_record.recap_end(ctx, "после 3.Nf3 у белых лишняя пешка") is None  # Nf3 is the 4th move here
    assert game_record.recap_end(_game("e4"), "е4") is None  # a lone bare square is no recap
    assert game_record.recap_end(CheckContext.from_fens(), "1.e4 e5") is None  # no game


def test_recap_in_russian_letters():
    ctx = _game(ST4)
    assert game_record.recap_end(ctx, "после 4.Кf3 Кf6 5.Сc4 exd4 6.O-O Кxe4") == 12


def test_captures_and_owner():
    ctx = _game("d4 e5 dxe5 Nc6 Nf3 Nf6 exf6 Be7 fxe7", color=chess.BLACK)
    caps = game_record.captures(ctx)
    assert [c.label for c in caps] == ["2.dxe5", "4.exf6", "5.fxe7"]
    assert all(c.mover == chess.WHITE and c.by_student is False for c in caps)
    assert [chess.piece_name(c.captured) for c in caps] == ["pawn", "knight", "bishop"]
    assert caps[-1].square == chess.E7


def test_en_passant_capture_square():
    ctx = _game("e4 a6 e5 d5 exd6")
    (cap,) = game_record.captures(ctx)
    assert cap.captured == chess.PAWN and cap.square == chess.D5 and cap.san == "exd6"


def test_last_capture_order():
    ctx = _game("d4 e5 dxe5 Nc6 Nf3 Nf6 exf6")
    assert game_record.last_capture(ctx).label == "4.exf6"  # the last ply played
    assert game_record.last_capture(ctx, told="а после 2.dxe5 ты отдал пешку").label == "2.dxe5"  # named in the sentence
    ctx2 = _game("d4 e5 dxe5 Nc6 Nf3 Nf6")
    assert game_record.last_capture(ctx2) is None  # the last two plies took nothing
    ctx2.scene_san = "dxe5"
    assert game_record.last_capture(ctx2).label == "2.dxe5"  # the move the answer last wrote


def test_exchanges_wc2021_game6():
    _, moves = _wc6_moves()
    runs = {e.start_ply: e for e in game_record.exchanges(moves)}
    q = next(e for e in runs.values() if e.sans[:1] == ("Qxc8",))
    assert q.text == "26.Qxc8 Rxc8 27.Rxc8"
    assert q.lost[chess.WHITE] == Counter({chess.QUEEN: 1}) and q.lost[chess.BLACK] == Counter({chess.ROOK: 2})
    r = next(e for e in runs.values() if e.sans[:1] == ("Rxf7+",))
    assert r.text == "80.Rxf7+ Kxf7 81.Rb7+ Kg6 82.Rxa7"  # the quiet check and its reply stay inside the run
    assert r.lost[chess.WHITE] == Counter({chess.ROOK: 1})
    assert r.lost[chess.BLACK] == Counter({chess.PAWN: 1, chess.BISHOP: 1})


def test_exchanges_from_san():
    runs = game_record.exchanges("e4 d5 exd5 Qxd5 Nc3".split())
    assert len(runs) == 1 and runs[0].sans == ("exd5", "Qxd5") and runs[0].start_ply == 3


def test_side_words():
    ctx = _game("e4 c5", color=chess.WHITE)
    assert game_record.side_words(ctx, "Чёрные отдали пешку") is chess.BLACK
    assert game_record.side_words(ctx, "ты взял пешку") is chess.WHITE
    assert game_record.side_words(ctx, "я взял пешку") is chess.BLACK
    assert game_record.side_words(ctx, "ақтар e5 сарбазын ұсынды") is chess.WHITE
    assert game_record.side_words(CheckContext.from_fens(), "ты взял") is None
    assert game_record.side_words(ctx, "конь прыгает") is None
    g, _ = _wc6_moves()
    rec = CheckContext.from_fens()
    rec.add_line(g["moves"])
    assert game_record.side_words(rec, "там Карлсен впервые отдал ладью за коня") is chess.WHITE
    assert game_record.side_words(rec, "Непомнящий ошибся") is chess.BLACK
    assert game_record.side_words(rec, "Nepomniachtchi blundered") is chess.BLACK


def test_material():
    m = game_record.material(chess.Board("4k3/8/8/8/8/8/PP6/R3K3 w - - 0 1"))
    assert (m["white"], m["black"], m["diff"]) == (7, 0, 7)
    assert m["more"] == {"white": {"R": 1, "P": 2}, "black": {}}
    assert game_record.material(chess.Board())["diff"] == 0


# ── board_math ───────────────────────────────────────────────────────────────────────────────────────────────────
_V = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}


def _old_see(board: chess.Board, move: chess.Move) -> int:
    """claim_rules.see as it was on main 02bb40d0, verbatim (the reference board_math.see must equal)."""
    t = move.to_square
    if board.is_en_passant(move):
        first = 1
    else:
        v = board.piece_at(t)
        first = _V[v.piece_type] if v else 0
    b = board.copy(stack=False)
    mover = b.piece_at(move.from_square)
    gains = [first]
    on_square = _V[mover.piece_type]
    b.push(move)
    side = b.turn
    while True:
        attackers = [s for s in b.attackers(side, t)
                     if chess.Move(s, t) in b.legal_moves or (b.piece_type_at(s) == chess.PAWN and chess.square_rank(t) in (0, 7))]
        if not attackers:
            break
        s = min(attackers, key=lambda x: _V[b.piece_type_at(x)])
        gains.append(on_square - gains[-1])
        on_square = _V[b.piece_type_at(s)]
        mv = next((m for m in b.legal_moves if m.from_square == s and m.to_square == t), None)
        if mv is None:
            break
        b.push(mv)
        side = b.turn
    for i in range(len(gains) - 1, 0, -1):
        gains[i - 1] = -max(-gains[i - 1], gains[i])
    return gains[0]


def test_see_equals_the_old_claim_rules_see_on_the_corpus():
    from src import claim_rules

    assert claim_rules.see is board_math.see
    positions = json.loads((FIX / "corpus_positions.json").read_text())["positions"]
    assert len(positions) == 318
    n = 0
    for p in positions:
        for b in (chess.Board(p["fen"]), board_math._as_side(chess.Board(p["fen"]), not chess.Board(p["fen"]).turn)):
            if b is None:
                continue
            for mv in b.legal_moves:
                if b.is_capture(mv):
                    assert board_math.see(b, mv) == _old_see(b, mv), (b.fen(), mv.uci())
                    n += 1
    assert n > 1000  # the captures of both sides on every position


def test_capture_is_free():
    # st2#4: after 3...Nf6 4.exf6 the pawn is taken back (gxf6 / Qxf6) — the knight is won, the pawn lost
    b = chess.Board()
    for m in "d4 e5 dxe5 Nc6 Nf3 Nf6".split():
        b.push_san(m)
    exf6 = b.parse_san("exf6")
    assert not board_math.capture_is_free(b, exf6) and board_math.see(b, exf6) == 2
    # exf4 in the King's Gambit: the f4 pawn is not defended — free
    k = chess.Board()
    for m in "e4 e5 f4".split():
        k.push_san(m)
    assert board_math.capture_is_free(k, k.parse_san("exf4"))
    assert not board_math.capture_is_free(chess.Board(), chess.Move.from_uci("e2e4"))


def test_legal_moves_reach_and_safe_squares():
    b = chess.Board()
    for m in "e4 c6 d4 d5 e5".split():
        b.push_san(m)
    assert len(board_math.legal_moves_of(b, chess.C8)) == 5  # Bc8 after 3.e5 is not locked: d7 e6 f5 g4 h3
    assert board_math.legal_moves_of(b, chess.E4) == []
    assert chess.D7 in board_math.reach(b, chess.C8) and len(board_math.reach(b, chess.E4)) == 0
    # g1-resign: the knight on f6 attacked by e5 has safe squares
    g = chess.Board()
    for m in "e4 Nf6 e5".split():
        g.push_san(m)
    safe = {chess.square_name(s) for s in board_math.safe_squares(g, chess.F6)}
    assert safe == {"d5", "e4", "g8"}  # g4 and h5 are on the queen's diagonal d1–h5, undefended
    # a trapped piece: the bishop on a7 (b8 is covered by the rook a8; Bxb6 is taken back by c7)
    t = chess.Board("r3k3/B1p5/1p6/8/8/8/8/4K3 w - - 0 1")
    assert board_math.safe_squares(t, chess.A7) == [] and len(board_math.legal_moves_of(t, chess.A7)) >= 1
    # a piece of the side not to move is judged for its own side
    assert board_math.legal_moves_of(t, chess.A8) and board_math.move_loss(t, t.parse_san("Bxb6")) == 2


# ── claim types ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_new_relations_and_presup():
    assert {"pin_exists", "locked", "cover_cause"} <= RELATIONS
    assert {"prevents", "retreat_cover"} <= RULE_RELATIONS
    assert "locked" not in OTHER_RELATIONS and "locked" in ALL_RELATIONS
    assert PRESUPS == ("", "before_move", "exists", "no_longer")
    c = Claim("pinned", Ref(sq="b1", piece="N", side=chess.WHITE), (), presup="before_move")
    d = c.to_dict()
    assert d["presup"] == "before_move" and Claim.from_dict(d) == c
    assert "presup" not in Claim("attack", None, ()).to_dict()
    assert Claim.from_dict({"rel": "attack", "subj": None, "objs": []}).presup == ""
    with pytest.raises(ValueError):
        Claim.from_dict({"rel": "attack", "subj": None, "objs": [], "presup": "maybe"})


def test_new_rule_relations_are_undecided_until_their_judge():
    from src.claim_judge import decide
    from src.claim_rules import RULE_JUDGES
    from src.claim_types import BoardSet

    assert set(RULE_JUDGES) == RULE_RELATIONS
    for rel in ("prevents", "retreat_cover", "pin_exists", "cover_cause"):
        c = Claim(rel, Ref(sq="d4", piece="P", side=chess.WHITE), (Ref(sq="d5"),))
        assert decide(c, BoardSet(chess.Board(), "on the board now"), None) == UNDECIDED


# ── turn facts ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_fact_type_and_ctx_facts():
    from src.turn_facts import Fact, given, quote

    f = Fact("piece_safety", "Nf6 is attacked by e5; safe squares: d5, g8, e4, g4", {"sq": "f6"}, "see")
    assert f.is_outcome and f.proven and Fact.from_dict(f.to_dict()) == f and hash(f)
    assert not Fact("fork", "a fork is available now: Qxd5+", {}, "board").proven
    with pytest.raises(ValueError):
        Fact("guess", "x")
    ctx = CheckContext.from_fens()
    assert ctx.facts == []
    ctx.facts = [f, Fact("material", "White is a pawn up", {}, "board")]
    assert given(ctx, "piece_safety") == [f] and len(given(ctx)) == 2
    assert quote(given(ctx, "piece_safety")) == " (you were given: Nf6 is attacked by e5; safe squares: d5, g8, e4, g4)"
    assert quote([]) == ""


# ── detector switches ────────────────────────────────────────────────────────────────────────────────────────────
PLAN_NAMES = {
    "book_wait", "recap_scope", "material_order", "student_capture", "gave_up", "block_kind", "free_capture",
    "propose_vocab", "plan_place", "start_scene", "open_plain", "open_recap", "open_character", "open_defining",
    "pin_escape", "pin_noun", "locked", "cover_cause", "idea_scope", "start_cue", "bare_pawn_line", "loaded_line",
    "retreat_cover", "prevents", "checks_geometry", "only_move_orders", "piece_decides", "trade_swing_named",
    "race_distance", "mate_squares", "king_direction", "trades",
}


def test_detector_names_and_defaults(monkeypatch):
    for k in ("COACH_DETECTORS_OFF", "COACH_DETECTORS_SHADOW", "COACH_TRADE_SWING_NAMED"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    monkeypatch.setattr(config, "COACH_TRADE_SWING_NAMED", False)
    assert set(config.DETECTOR_DEFAULTS) == PLAN_NAMES
    shadow = {n for n in PLAN_NAMES if config.detector_mode(n) == "shadow"}
    assert shadow == {"open_character", "open_defining", "loaded_line", "king_direction", "pin_noun", "bare_pawn_line"}
    assert {n for n in PLAN_NAMES if config.detector_mode(n) == "off"} == {"trade_swing_named"}
    assert config.detector_mode("no_such_detector") == "off"


def test_detector_switches(monkeypatch):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    monkeypatch.setenv("COACH_DETECTORS_OFF", " gave_up ,trades")
    monkeypatch.setenv("COACH_DETECTORS_SHADOW", "free_capture,gave_up")
    assert config.detector_mode("gave_up") == "off" and config.detector_mode("trades") == "off"
    assert config.detector_mode("free_capture") == "shadow" and not config.detector_on("free_capture")
    assert config.detector_enabled("free_capture") and config.detector_on("recap_scope")
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "shadow")
    assert config.detector_mode("pin_escape") == "shadow" and config.detector_mode("recap_scope") == "on"
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "off")
    assert config.detector_mode("prevents") == "off" and config.detector_mode("race_distance") == "on"


def test_detectors_stay_out_of_the_lesson_tutor_and_relations_shadow_in_move_comments(monkeypatch):
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW", raising=False)
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    lesson, game = CheckContext.from_fens(), CheckContext.from_fens()
    lesson.relation_surface, game.relation_surface = "lesson", "game"
    assert all(config.detector_mode(n, lesson) == "off" for n in PLAN_NAMES)
    # fix 01.11: a move comment caps the relation detectors only; the others judge it as a chat answer
    assert config.detector_mode("recap_scope", game) == "on"
    assert all(config.detector_mode(n, game) == "shadow" for n in config.RELATION_DETECTORS
               if config.detector_mode(n) == "on")


def test_trade_swing_named_needs_its_flag(monkeypatch):
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW", raising=False)
    monkeypatch.delenv("COACH_TRADE_SWING_NAMED", raising=False)
    monkeypatch.setattr(config, "COACH_TRADE_SWING_NAMED", False)
    assert config.detector_mode("trade_swing_named") == "off"
    monkeypatch.setenv("COACH_TRADE_SWING_NAMED", "1")
    assert config.detector_mode("trade_swing_named") == "on"
    monkeypatch.setenv("COACH_DETECTORS_OFF", "trade_swing_named")
    assert config.detector_mode("trade_swing_named") == "off"


def test_config_keys():
    assert config.COACH_TRADE_SWING_NAMED in (True, False)
    assert config.COACH_TURN_FACTS in (True, False)
    assert config.STOCKFISH_POOL in (True, False) and config.COACH_PRECOMPUTE in (True, False)
    assert config.STOCKFISH_POOL_SIZE >= 1 and config.STOCKFISH_HASH_MB >= 1 and config.STOCKFISH_RECYCLE_SEARCHES >= 1


# ── hooks (stubs behave as main did) ─────────────────────────────────────────────────────────────────────────────
def test_trade_hook_is_called_and_fail_open(monkeypatch):
    import src.trade_claims as tc

    g, _ = _wc6_moves()
    ctx = CheckContext.from_fens()
    ctx.add_line(g["moves"])
    s = "там был красивый размен, где белые отдали ферзя за ладью и получили решающий эндшпиль."
    # P6 filled the stub (plan 31.10): the WC2021 g6 claim is judged against the game's exchanges
    assert any("two rooks" in i for i in tc.trade_issues(s, ctx))
    seen = []
    monkeypatch.setattr(tc, "trade_issues", lambda text, c: seen.append(text) or ["the trade is wrong"])
    assert "the trade is wrong" in check_sentence(s, CheckContext.from_fens()) and seen

    def boom(text, c):
        raise RuntimeError("broken")

    monkeypatch.setattr(tc, "trade_issues", boom)
    assert check_sentence("Конь f3 прыгает на g5.", CheckContext.from_fens()) == []


def test_rules_block_board_verdicts_stub():
    from src.rules_facts import rules_block

    q = "Пат — это ничья?"
    assert rules_block(q) and "Stalemate" in rules_block(q)
    assert rules_block(q, board_verdicts={"fen": None, "ideas": [{"san": "Qb4", "draw": True}], "idea_fens": [],
                                          "engine_lines": []}) == ""


def test_searchmoves_separate_the_cache(monkeypatch):
    from src.tools import stockfish

    stockfish.clear_analysis_cache()
    calls = []

    def fake(fen, depth, multipv, path, timeout, movetime, cap=None, searchmoves=()):
        calls.append(searchmoves)
        pv = searchmoves[0] if searchmoves else "b1c3"
        return {"lines": [{"pv": pv, "score": 0.5, "depth": 14}], "best_move": pv, "evaluation": 0.5}

    monkeypatch.setattr(stockfish, "_analyze_position", fake)
    monkeypatch.setattr(stockfish, "ENGINE_API_URL", "")
    fen = "r1bq1b1r/ppp3pp/2n1k3/3np3/2B5/5Q2/PPPP1PPP/RNB1K2R w KQ - 2 8"
    a = stockfish.analyze_timed(fen, 300, multipv=1)
    q = stockfish.analyze_timed(fen, 300, multipv=1, searchmoves=["f3g3", "f3d5", "bogus"])
    assert a["lines"][0]["pv"] == "b1c3" and q["lines"][0]["pv"] == "f3d5"
    assert calls == [(), ("f3d5", "f3g3")]
    # cached under their own keys: the same requests again start no search, in any order of the moves
    assert stockfish.analyze_timed(fen, 300, multipv=1, searchmoves=("f3g3", "f3d5"))["lines"][0]["pv"] == "f3d5"
    assert stockfish.analyze_timed(fen, 300, multipv=1)["lines"][0]["pv"] == "b1c3"
    assert stockfish.analyze_cached(fen, depth=12, multipv=1, searchmoves=["f3d5"])["lines"][0]["pv"] == "f3d5"
    assert len(calls) == 3
    assert stockfish._cache_key(fen) != stockfish._cache_key(fen, ["f3g3"])
    stockfish.clear_analysis_cache()


class _FakeProc:
    """A Stockfish stand-in for _analyze_position: records what it is sent, answers one line."""

    sent: list = []

    def __init__(self, *a, **k):
        self.stdin = self
        self.stdout = self
        self._lines = iter(["info depth 5 multipv 1 score cp 10 pv f3g3\n", "bestmove f3g3\n"])

    def write(self, s):
        _FakeProc.sent.append(s)

    def flush(self):
        pass

    def readline(self):
        return next(self._lines, "")

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


def test_searchmoves_reach_the_engine_command(monkeypatch):
    import subprocess

    from src.tools import stockfish

    _FakeProc.sent = []
    monkeypatch.setattr(subprocess, "Popen", _FakeProc)
    fen = "8/8/8/8/8/8/8/K6k w - - 0 1"
    res = stockfish._analyze_position(fen, 5, 1, "stockfish", 5, 100, None, searchmoves=("a1a2", "a1b1"))
    assert "go movetime 100 searchmoves a1a2 a1b1\n" in _FakeProc.sent and res["best_move"] == "f3g3"
    _FakeProc.sent = []
    stockfish._analyze_position(fen, 5, 1, "stockfish", 5, 100, None)
    assert "go movetime 100\n" in _FakeProc.sent  # without searchmoves the command is main's, byte for byte


def test_health_reports_the_book_index(monkeypatch):
    from fastapi.testclient import TestClient

    from src import answer_check_facts, server

    body = TestClient(server.app).get("/health").json()
    assert "book_index_ready" in body and isinstance(body["book_index_ready"], bool)
    answer_check_facts.warm_book_index()
    from src.openings_book import warm_position_index

    warm_position_index()
    assert TestClient(server.app).get("/health").json()["book_index_ready"] is True
