"""P3A of plan 31.10 (detect-1031): the relations a sentence takes for granted, read by claim_grammar.

  pin_escape   «Nd2: конь уходит из-под связки» → pinned(the knight) on the board before Nd2 (presup before_move);
               «снять/убрать связку», «увести короля из-под связки», «развязать пешку c5» → pin_exists (some board)
  pin_noun     «держать/сохранить/усилить связку», «под связку» → pin_exists (shadow on its first run)
  locked       «слон c8 заперт» with no blocker named → locked(the bishop), once the judge reads «no way out»
  cover_cause  «поле f6 держала пешка g7, и конь там потерялся» → cover_cause(g7, f6, the knight lost there)

The judges of these claims are P3B's (claim_judge): WP-0's judge leaves pin_exists, cover_cause and the before_move
pin undecided, so on its own this package cuts nothing new. ``ref_judges`` below stands in for P3B's semantics
(PLAN §3: pin_exists true on any board of the scene; before_move judged on the board before the told move; locked =
at most one legal move or one square of reach; cover_cause false when the holder is the lost piece's colour) to
show the claims carry what those judges need — the rows plan-caro-adv and op-ruy are caught with it, the true
controls stay clean.
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import chess
import pytest

from src import claim_grammar as cg
from src import claim_judge as J
from src.claim_types import Claim, Ref

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
from ctx_fixture import load_ctx, run_answer  # noqa: E402

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "detect1031"
P3A = ("pin_escape", "pin_noun", "locked", "cover_cause")


def _mine(text: str, state=None) -> list:
    return [c for c in cg.extract(text, {} if state is None else state) if c.kind in P3A]


def _one(text: str) -> Claim:
    got = _mine(text)
    assert len(got) == 1, [c.to_dict() for c in got]
    return got[0]


# ── the stand-in for P3B's judges (test only) ────────────────────────────────────────────────────────────────────
@pytest.fixture
def ref_judges(monkeypatch):
    """P3B's semantics of P3A's claims, patched into claim_judge for the test; 'shadow' detectors are undecided."""
    from src import config
    from src.claim_scene import board_before, last_move
    from src.game_record import captures

    forced: set = set()

    def live(claim):
        return claim.kind not in config.DETECTOR_DEFAULTS or claim.kind in forced or \
            config.detector_mode(claim.kind) == "on"

    def matches(board, claim):
        for t in board.piece_map():
            for a in J._pinners(board, t):
                b = J.pin_behind(board, a, t)
                s, o, k = claim.subj, next((x for x in claim.objs if x is not None), None), claim.to
                if s is not None and ((s.sq and chess.parse_square(s.sq) != a) or
                                      (s.piece and board.piece_type_at(a) != J.PIECE_TYPE[s.piece]) or
                                      (s.side is not None and board.color_at(a) != s.side)):
                    continue
                if o is not None and ((o.sq and chess.parse_square(o.sq) != t) or
                                      (o.piece and board.piece_type_at(t) != J.PIECE_TYPE[o.piece]) or
                                      (o.side is not None and board.color_at(t) != o.side)):
                    continue
                if k is not None and ((k.piece and board.piece_type_at(b) != J.PIECE_TYPE[k.piece]) or
                                      (k.side is not None and board.color_at(b) != k.side)):
                    continue
                return True
        return False

    def pin_exists(claim, board, ctx):
        if not live(claim):
            raise J._Undecided
        if claim.presup == "before_move":
            board = board_before(board)
            if board is None:
                raise J._Undecided
        return (True, "") if matches(board, claim) else (False, "nothing is pinned")

    orig_pinned, orig_locked = J._JUDGES["pinned"], J._JUDGES["locked"]

    def pinned(claim, board, ctx):
        if claim.presup != "before_move" or claim.move is None:
            return orig_pinned(claim, board, ctx)
        if not live(claim):
            raise J._Undecided
        mv, prev = last_move(board), board_before(board)
        if mv is None or prev is None or chess.square_name(mv.to_square) != claim.move.to:
            raise J._Undecided
        c = replace(claim, objs=(Ref(sq=chess.square_name(mv.from_square), piece=claim.objs[0].piece),), presup="",
                    move=None)
        v, truth = orig_pinned(c, prev, ctx)
        return v, (f"before {prev.san(mv)}: {truth}" if v is False else truth)

    def locked(claim, board, ctx):
        if claim.rel != "locked" or claim.objs:
            return orig_locked(claim, board, ctx)
        if not live(claim):
            raise J._Undecided
        a = chess.parse_square(claim.subj.sq)
        moves = J._moves_of(board, a)
        if moves is None or board.piece_type_at(a) in (None, chess.KING, chess.PAWN):
            raise J._Undecided
        if len(moves) <= 1 or len(board.attacks(a)) <= 1:
            return True, ""
        return False, f"{J.who(board, a)} can go to {J._sqnames({m.to_square for m in moves})}"

    def cover_cause(claim, board, ctx):
        if not live(claim):
            raise J._Undecided
        z = claim.objs[0].sq
        hp = board.piece_at(chess.parse_square(claim.subj.sq))
        caps = [c for c in captures(ctx) if chess.square_name(c.square) == z]
        if hp is None or not caps:
            raise J._Undecided
        if hp.color != caps[-1].mover:
            return False, f"{J.who(board, chess.parse_square(claim.subj.sq))} is {J._side(hp.color)}'s own piece; " \
                          f"the {J.NAME[caps[-1].captured]} on {z} was taken by {caps[-1].label}"
        return True, ""

    monkeypatch.setitem(J._JUDGES, "pin_exists", pin_exists)
    monkeypatch.setitem(J._JUDGES, "pinned", pinned)
    monkeypatch.setitem(J._JUDGES, "locked", locked)
    monkeypatch.setitem(J._JUDGES, "cover_cause", cover_cause)
    return forced


def _row(rid: str) -> dict:
    return json.loads((FIX / "rows" / f"{rid}.json").read_text(encoding="utf-8"))


def _run_row(rid: str):
    row = _row(rid)
    return run_answer(row["prefix"] + [row["sentence"]], load_ctx(row["ctx"]), live_game=row["turn"].get("live_game"))


# ── pin_escape ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_escape_with_its_move_is_a_pin_before_the_move():
    c = _one("Играй Nd2: конь уходит из-под связки, а слон чёрных на f5 остаётся «в воздухе».")
    assert (c.rel, c.presup, c.kind) == ("pinned", "before_move", "pin_escape")
    assert c.move.san == "Nd2" and [m.san for m in c.pos.moves] == ["Nd2"] and c.pos.at == "after"
    # the piece has no square: the judge reads the one that made the move, on the board before it — on any other
    # board (WP-0's judge, an alternative) the claim binds to nothing and stays undecided
    assert c.objs == (Ref(piece="N", text="конь"),)
    assert Claim.from_dict(json.loads(json.dumps(c.to_dict()))) == c


def test_escape_without_a_move_is_judged_on_the_board_named():
    c = _one("Конь c3 уходит из-под связки.")
    assert (c.rel, c.presup, c.pos.at, c.move) == ("pinned", "", "now", None)
    assert c.objs[0].sq == "c3" and c.objs[0].piece == "N"


def test_past_escape_without_a_move_and_proposals_presuppose_some_pin():
    c = _one("Конь ушёл из-под связки.")
    assert (c.rel, c.presup, c.pos.tense) == ("pin_exists", "exists", "past")
    c = _one("Король d6 спешит к полю e6, чтобы развязать пешку c5.")
    assert (c.rel, c.presup) == ("pin_exists", "exists") and c.objs[0].sq == "c5" and c.objs[0].piece == "P"
    c = _one("Сначала убери связку.")
    assert (c.rel, c.presup) == ("pin_exists", "exists") and c.objs == (Ref(owner="you"),)
    c = _one("У чёрных два способа снять связку.")
    assert c.objs == (Ref(side=chess.BLACK),)


def test_the_king_escaping_means_a_piece_pinned_to_it():
    c = _one("Белый король увёл ферзя из-под связки.")
    assert c.rel == "pin_exists" and c.to.piece == "K" and c.to.side is chess.WHITE
    assert c.objs[0].piece == "Q" and c.objs[0].side is chess.WHITE
    c = _one("Kh1: король уходит из-под связки.")
    assert (c.rel, c.presup, c.move.san) == ("pin_exists", "before_move", "Kh1") and c.to.piece == "K"
    c = _one("Что, по-твоему, стоит сделать — отогнать слона или увести короля из-под связки?")
    assert (c.rel, c.presup) == ("pin_exists", "exists") and c.to.piece == "K"


@pytest.mark.parametrize("text", [
    "Развязка партии наступила только на тридцатом ходу.",  # the dénouement
    "Вопрос к тебе: тебе эта разменная развязка нравится?",
    "ручей развязывает узлы,",  # no piece
    "Что из этого стоит развязать первым?",  # no piece named
    "Сыграй Фc2 — королева уходит с линии связки и заодно поддерживает будущий e4.",  # leaves the line, not the pin
    "Первый ход — Ng6+, и это единственный путь к мату: всё держится на связке пешки h7.",  # «держится на»
    "Если ферзь попробует взяться за неё — он попадёт под связку от слона c1.",  # conditional future
    "Нет никакой связки, конь спокойно уходит.",
    "Связка — это когда фигура не может уйти, не открыв более ценную.",  # a definition
    "Обычно слон уходит из-под связки ходом назад.",  # a rule
    "Белые готовят g4 и хотят избежать связки ...Сg4, но теряют темп.",  # the existing pin_after
])
def test_no_presupposed_pin(text):
    assert not [c for c in _mine(text) if c.kind in ("pin_escape", "pin_noun")]


# ── pin_noun ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_holding_a_pin_names_its_holder():
    c = _one("Кстати, а что ты вообще хочешь получить от этого слона — держать связку или менять на c6?")
    assert (c.rel, c.presup, c.kind) == ("pin_exists", "exists", "pin_noun")
    assert c.subj.piece == "B" and c.objs == ()
    c = _one("Кстати, заметьте: слон на c4 уже держит связку по f7, а ладья d8 — по e8.")
    assert c.subj.sq == "c4" and c.objs[0].sq == "f7"
    c = _one("Чёрные сохраняют связку и давят на e4.")
    assert c.subj == Ref(side=chess.BLACK) and c.objs == ()
    c = _one("Заодно ты подставляешь свою ладью a8 под связку.")
    assert c.rel == "pin_exists" and c.objs[0].sq == "a8" and c.objs[0].piece == "R"


def test_switches_turn_each_detector_off(monkeypatch):
    monkeypatch.setenv("COACH_DETECTORS_OFF", "pin_escape,pin_noun,cover_cause")
    assert not _mine("Играй Nd2: конь уходит из-под связки.")
    assert not _mine("Кстати, а что ты хочешь от этого слона — держать связку?")
    assert not _mine("Поле f6 держала пешка g7, и конь там просто потерялся.")
    monkeypatch.setenv("COACH_DETECTORS_OFF", "")
    monkeypatch.setenv("COACH_DETECTORS_SHADOW", "pin_escape")
    assert _mine("Играй Nd2: конь уходит из-под связки.")  # shadow still emits: the judge records, never cuts


# ── locked ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_locked_waits_for_the_judge_of_no_way_out():
    # WP-0's judge reads «locked» as «no legal move at all» and would cut the French bishop: nothing is emitted
    assert not cg._locked_judge_ready()
    assert not _mine("Слон c8 заперт.")


def test_locked_is_emitted_once_the_judge_reads_no_way_out(ref_judges):
    assert cg._locked_judge_ready()
    c = _one("Слон c8 заперт.")
    assert (c.rel, c.subj.sq, c.subj.piece, c.objs) == ("locked", "c8", "B", ())
    two = _mine("Смотри на фигуры: конь на g1 и слон на f1 пока заперты.")
    assert sorted((c.subj.sq, c.subj.piece) for c in two) == [("f1", "B"), ("g1", "N")]


@pytest.mark.parametrize("text", [
    "Слон c8 заперт пешками e6 и d5.",  # blockers named: locked_by
    "Слон c8 всё ещё заперт за своими пешками.",
    "Король на g8 заперт своими же пешками f7, g7, h7.",  # a king's net
    "Чёрный король заперт в углу.",
    "Kd6, затем a6 — Kc6, a7 — Kb7, и пешка заперта.",  # a blocked pawn
    "Чёрный ферзь оказывается заперт — любое его отступление наталкивается на твою ладью.",  # trapped
    "Пока он не заперт за своими пешками, слон выйдет на f5.",
])
def test_not_a_locked_claim(text, ref_judges):
    assert not [c for c in _mine(text) if c.kind == "locked"]
    if "пешками e6" in text:
        assert [c.rel for c in cg.extract(text, {})] == ["locked_by"]


# ── cover_cause ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_hold_named_as_the_cause_of_a_loss():
    c = _one("Это была ошибка: поле f6 держала пешка g7, и конь там просто потерялся — белые забирают фигуру бесплатно.")
    assert (c.rel, c.kind) == ("cover_cause", "cover_cause")
    assert (c.subj.sq, c.subj.piece) == ("g7", "P") and c.objs == (Ref(sq="f6"),)
    assert (c.to.sq, c.to.piece) == ("f6", "N")


@pytest.mark.parametrize("text", [
    "Поле f6 держала пешка g7, и конь там не потерялся.",
    "Конь f6 потерялся.",  # no hold named
    "Поле f6 держала пешка g7, а конь d4 потерялся.",  # lost elsewhere
])
def test_no_cover_cause(text):
    assert not [c for c in _mine(text) if c.kind == "cover_cause"]


# ── the rows, with P3B's semantics ───────────────────────────────────────────────────────────────────────────────
def test_plan_caro_adv_is_caught_by_the_pin_before_nd2(ref_judges):
    sentence, issues, stage = _run_row("plan-caro-adv")[-1]
    assert stage == "sync" and len(issues) == 1
    assert "before Nd2" in issues[0] and "knight on b1 is not pinned" in issues[0]


def test_op_ruy_is_caught_when_pin_noun_is_on(ref_judges):
    assert _run_row("op-ruy")[-1][1] == []  # pin_noun ships in shadow (PLAN §7): recorded, not cut
    ref_judges.add("pin_noun")
    sentence, issues, stage = _run_row("op-ruy")[-1]
    assert stage == "sync" and issues


def test_st2_4_cover_cause_names_the_real_capture(ref_judges):
    issues = _run_row("st2_4-attack")[-1][1]
    assert any("g7 is Black's own piece" in i and "4.exf6" in i for i in issues)


def _control_ctx(c: dict):
    from src.answer_check import CheckContext

    moves = c["moves"].split() if c.get("moves") else None
    fen = c.get("fen")
    if moves:
        b = chess.Board()
        for m in moves:
            b.push_san(m)
        fen = b.fen()
    ctx = CheckContext.from_fens([fen], [" ".join(moves)] if moves else [], question=c.get("question") or "")
    if moves:
        ctx.game_moves = moves
    ctx.language = "ru"
    return ctx


NEG = json.loads((FIX / "negatives" / "P3A.json").read_text(encoding="utf-8"))["controls"] + \
    [c for c in json.loads((FIX / "negatives" / "P3B.json").read_text(encoding="utf-8"))["controls"]
     if c.get("detector") in ("locked", "cover_cause")]


@pytest.mark.parametrize("control", NEG, ids=[c["id"] for c in NEG])
def test_true_controls_stay_clean_with_p3b_semantics(control, ref_judges):
    ref_judges.update({"pin_noun"})  # judge the shadow detector as if it were on
    got = run_answer(list(control.get("before") or []) + [control["sentence"]], _control_ctx(control))
    assert got[-1][1] == [], f"{control['id']}: {got[-1][1]} — {control['why']}"


@pytest.mark.parametrize("control", [c for c in NEG if c.get("emits")], ids=[c["id"] for c in NEG if c.get("emits")])
def test_true_controls_do_carry_the_claim(control, ref_judges):
    """A control is a check of the judge only when the grammar reads the presupposition in it."""
    assert any(c.kind == control["detector"] for c in cg.extract(control["sentence"], {}))
