"""Board-rule relations (src/claim_rules.py, plan 30.10 WP-D): the extractor's claims and the judges' verdicts.

Until WP-B's resolver and judge are merged, the boards come from ``local_boards`` below — the llm design's
``resolve`` (tests/support/ref_judge.py) on claim_types — and the reporting rule of plan §3.1 is ``local_decide``:
false on the primary board, true on no alternative, judgeable on the shown board. ``local_judge`` is the seam the
measurement (scripts/eval_relations.py with ``acr.judge_claim`` patched) uses for the rule relations.

The cases are in tests/fixtures/relations/rules_cases.json: the triage findings this package owns (positive: a
false claim, judged false on its board) and true sentences of the same relations from the production answers and
the eval set (negative: no claim, or no claim judged false).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import chess
import pytest

from src import answer_check as ac
from src import claim_rules as R
from src.claim_types import RULE_RELATIONS, UNDECIDED, BoardSet, Claim, MoveRef, Ref, Verdict

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "relations"
CASES = json.loads((FIX / "rules_cases.json").read_text())


# ── the local resolver and the reporting rule (stand-ins for claim_scene / claim_judge until WP-B merges) ──────
def _play(board: chess.Board, m: MoveRef) -> Optional[chess.Board]:
    """*board* after *m*: legal now; for the side not to move (an idea move, after a pass); a move already on the
    board (the piece stands there) is skipped. None when it cannot be played."""
    def parse(b):
        try:
            if m.castle:
                return b.parse_san("O-O" if m.castle == "short" else "O-O-O")
            if m.san:
                mv = b.parse_san(m.san.rstrip("!?"))
                return mv if not m.capture or b.is_capture(mv) else None
            cands = [x for x in b.legal_moves if chess.square_name(x.to_square) == m.to
                     and b.piece_type_at(x.from_square) == chess.Piece.from_symbol(m.piece or "P").piece_type]
            return cands[0] if len(cands) == 1 else None
        except ValueError:
            return None

    mv = parse(board)
    b = board
    if mv is None and not board.is_check():
        b = board.copy(stack=False)
        b.push(chess.Move.null())
        mv = parse(b)
    if mv is None:
        p = board.piece_at(chess.parse_square(m.to)) if m.to else None
        if p is not None and p.piece_type == chess.Piece.from_symbol(m.piece or "P").piece_type:
            return board
        return None
    b = b.copy(stack=False)
    b.push(mv)
    return b


def _shown(ctx) -> list:
    cur = ctx._key(ctx.current) if ctx.current is not None else None
    keys = (ctx.state_keys - ctx.line_keys - ctx.other_board_keys) - {cur, ctx._key(chess.Board())}
    return [b for b in ctx.boards if ctx._key(b) in keys]


def local_boards(claim: Claim, ctx, state: dict) -> Optional[BoardSet]:
    pos = claim.pos
    if pos.at in ("skip", "plan", "back", "shown_after", "then") or ctx.current is None:
        return None  # «then» and the past are WP-B's (the end of the scene before, the game)
    if pos.tense == "past" and not pos.moves:
        return None  # the past with no line: WP-B looks into the game; the local stand-in does not
    shown = _shown(ctx)
    if pos.at == "shown":
        return BoardSet(primary=shown[0], where="on the board shown", shown=shown[0]) if shown else None
    def walk(moves):
        for base in [ctx.current] + shown:
            b = base
            for m in moves:
                b = _play(b, m)
                if b is None:
                    break
            if b is not None:
                return b
        return None

    b = walk(pos.moves)
    if b is None:
        return None
    where = "after " + " ".join(m.san or (m.to or "") for m in pos.moves) if pos.moves else "on the board now"
    alts = (tuple(shown) if not pos.moves else ()) + tuple(x for x in (walk(a.moves) for a in pos.alts) if x is not None)
    return BoardSet(primary=b, where=where, alternatives=alts, shown=shown[0] if shown and not pos.moves else None)


def local_decide(claim: Claim, boards: BoardSet, ctx) -> Verdict:
    judge = R.RULE_JUDGES[claim.rel]
    v = judge(claim, boards.primary, ctx)
    if v.status != "false":
        return v
    for alt in boards.alternatives:
        if judge(claim, alt, ctx).status == "true":
            return UNDECIDED
    if boards.shown is not None and judge(claim, boards.shown, ctx).status == "undecided":
        return UNDECIDED
    return Verdict("false", boards.where, v.truth)


def local_judge(claim: Claim, ctx, state: dict) -> Optional[Verdict]:
    if claim.rel not in RULE_RELATIONS:
        return None
    boards = local_boards(claim, ctx, state)
    return None if boards is None else local_decide(claim, boards, ctx)


def _ctx(case: dict):
    color = {"w": chess.WHITE, "b": chess.BLACK}.get(case.get("student"))
    ctx = ac.CheckContext.from_fens([case["fen"], case.get("shown")], question=case.get("question") or "",
                                    student_color=color)
    if case.get("game_moves"):
        ctx.game_moves = list(case["game_moves"])
    return ctx


def _run(case: dict) -> list:
    """[(sentence, claim, verdict)] for every sentence of the case, state carried as in an answer."""
    ctx = _ctx(case)
    state = ctx.relation_state  # as the answer check passes it: the judges read what extract left there
    out = []
    sents = case.get("sentences") or [case["sentence"]]
    for s in case.get("before", []) + sents:
        claims = R.extract(s, state)
        if s not in sents:
            continue
        for c in claims:
            out.append((s, c, local_judge(c, ctx, state)))
    return out


# ── the cases ─────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("case", CASES["positive"], ids=[c["id"] for c in CASES["positive"]])
def test_a_false_rule_claim_is_found_and_judged_false(case):
    got = _run(case)
    false = [(s, c, v) for s, c, v in got if v is not None and v.status == "false"]
    assert false, f"no false claim in {case['id']}: {[(c.to_dict(), v) for _, c, v in got]}"
    want = case["expect"]
    hits = [(c, v) for _, c, v in false if c.rel == want["rel"] and (not want.get("kind") or c.kind == want["kind"])]
    assert hits, [(c.to_dict(), v) for _, c, v in false]
    for word in want.get("truth_has", []):
        assert any(word in v.truth for _, v in hits), [v.truth for _, v in hits]
    for s, c, v in got:  # the true parts of the same sentences stay true
        if any(c.rel == t["rel"] and c.kind == t.get("kind", c.kind) for t in case.get("also_true", [])) and \
                not (c.rel == want["rel"] and c.kind == want.get("kind", c.kind)):
            assert v is not None and v.status == "true", (c.to_dict(), v)


@pytest.mark.parametrize("case", CASES["negative"], ids=[c["id"] for c in CASES["negative"]])
def test_a_true_rule_claim_is_not_reported(case):
    got = _run(case)
    if case.get("only_rel_kind"):  # a sentence that also holds a false claim: only its true part is this case
        rel, kind = case["only_rel_kind"]
        got = [(s, c, v) for s, c, v in got if c.rel == rel and c.kind == kind and c.move is None]
    false = [(c.to_dict(), v.truth) for _, c, v in got if v is not None and v.status == "false"]
    assert not false
    if case.get("judged"):
        assert any(v is not None and v.status == "true" for _, _, v in got), [(c.to_dict(), v) for _, c, v in got]


@pytest.mark.parametrize("case", CASES["no_claim"], ids=[c["id"] for c in CASES["no_claim"]])
def test_words_that_are_not_a_rule_claim(case):
    state: dict = {}
    for s in case.get("before", []):
        R.extract(s, state)
    assert R.extract(case["sentence"], state) == []


def test_every_rule_relation_has_a_judge_and_every_claim_is_a_rule_claim():
    assert set(R.RULE_JUDGES) == RULE_RELATIONS
    for case in CASES["positive"] + CASES["negative"]:
        state: dict = {}
        for s in case.get("before", []) + (case.get("sentences") or [case["sentence"]]):
            for c in R.extract(s, state):
                assert c.source == "rules" and c.rel in RULE_RELATIONS
                assert Claim.from_dict(c.to_dict()) == c


# ── the d2 line: the board before a move of the line the answer wrote ───────────────────────────────────────────
D2 = "kr6/2pn1p2/p6p/P2Pp3/N1P5/7B/3Q1PPP/6K1 b - - 0 33"
D2_SENTENCES = ["Решение: 33...Rb1+ 34.Qc1 Rxc1#.", "Ладья бьёт по первой горизонтали с шахом — Rb1+. ",
                "Белый король на g1 далеко, и закрыться может только ферзь: 34.Qc1 — d2–c1.",
                "Но это как раз то, что нужно чёрным: ладья на b1 забирает ферзя на c1 и ставит мат — b1–c1. ",
                "Ферзь был единственной защитой, а теперь он сам загородил королю последний выход.",
                "Как думаешь, почему белый ферзь просто обязан был встать на c1, у него не было выбора? "]


def test_d2_only_block_the_queen_part_true_the_move_part_false():
    ctx = ac.CheckContext.from_fens([D2])
    state = ctx.relation_state
    verdicts = {}
    for s in D2_SENTENCES:
        for c in R.extract(s, state):
            verdicts[(D2_SENTENCES.index(s), c.rel, c.kind, c.move is not None)] = local_judge(c, ctx, state)
    assert verdicts[(2, "only_move", "block", False)].status == "true"  # only the queen can block
    only = verdicts[(2, "only_move", "block", True)]
    assert only.status == "false" and "Qc1, Qd1 and Qe1" in only.truth and only.where == "after Rb1+"
    assert verdicts[(4, "only_move", "parry", False)].status == "true"  # the queen was the only defence
    escape = verdicts[(4, "no_flight", "blocker", False)]
    assert escape.status == "false" and "queen on c1" in escape.truth and "king on g1" in escape.truth
    obliged = verdicts[(5, "only_move", "any", True)]
    assert obliged.status == "false" and "Qd1" in obliged.truth and "Qe1" in obliged.truth


def test_a_sentence_repeating_a_move_continues_the_line_it_belongs_to():
    state: dict = {}
    R.extract("Решение: 33...Rb1+ 34.Qc1 Rxc1#.", state)
    R.extract("Ферзь идёт на c1: 34.Qc1.", state)
    assert [m.san for m in state["rules_lines"][-1]] == ["Rb1+", "Qc1"]
    R.extract("Совсем другая идея: Nf3 и Ng5.", state)
    assert [m.san for m in state["rules_lines"][-1]] == ["Nf3", "Ng5"]


def test_bare_squares_are_moves_only_inside_a_written_line():
    assert [m.san for _, _, m in R._moves(R._prep("1.e4 e5 2.Nf3 Nc6"))] == ["e4", "e5", "Nf3", "Nc6"]
    assert [m.san for _, _, m in R._moves(R._prep("пешка на e5 и конь на f3"))] == []


# ── the judges on fixed boards ───────────────────────────────────────────────────────────────────────────────
def _claim(rel, subj=None, objs=(), **kw):
    return Claim(rel=rel, subj=subj, objs=tuple(objs), source="rules", **kw)


def test_can_capture_en_passant_and_the_side_not_to_move():
    b = chess.Board("rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3")
    c = _claim("can_capture", Ref(side=chess.WHITE), [Ref(sq="f5")])
    assert R.judge_can_capture(c, b, None).status == "true"  # exf6 e.p. takes the pawn on f5
    c = _claim("can_capture", Ref(side=chess.BLACK), [Ref(sq="e5")])
    assert R.judge_can_capture(c, b, None).status == "false"  # nothing of Black's reaches e5 (after a pass)
    c = _claim("can_capture", Ref(sq="d5", piece="P"), [Ref(sq="e4")])
    assert R.judge_can_capture(c, b, None).status == "false" and "e4 is empty" in R.judge_can_capture(c, b, None).truth


def test_can_capture_respects_a_pin_to_the_king():
    b = chess.Board("4k3/3n4/8/1B3P2/8/8/8/4K3 b - - 0 1")  # knight d7 pinned by the bishop b5
    c = _claim("can_capture", Ref(sq="d7", piece="N"), [Ref(sq="f6")])
    assert R.judge_can_capture(c, b, None).status == "false"
    c = _claim("can_capture", Ref(sq="d7", piece="N"), [Ref(sq="b6")])
    assert R.judge_can_capture(c, b, None).status == "false"


def test_exchange_count_on_one_square():
    b = chess.Board("r1bqkb1r/pp3pp1/2nppn1p/2p5/2B1P3/3P1N1P/PPP2PP1/RNBQ1RK1 w kq - 1 7")
    c = _claim("can_exchange", Ref(side=chess.BLACK), [Ref(sq="e4")])
    v = R.judge_can_exchange(c, b, None)
    assert v.status == "false" and "Nxe4 loses 2 points" in v.truth
    # an even trade: the knight on c6 for the knight on d4
    b = chess.Board("r1bqkbnr/pppp1ppp/2n5/8/3NP3/8/PPP2PPP/RNBQKB1R b KQkq - 0 4")
    c = _claim("can_exchange", Ref(side=chess.BLACK), [Ref(sq="d4")])
    assert R.judge_can_exchange(c, b, None).status == "true"
    assert R.see(b, b.parse_san("Nxd4")) == 0


def test_no_flight_is_judged_only_for_the_king_that_has_to_move():
    mated = chess.Board("3R2k1/5ppp/8/8/8/8/5PPP/6K1 b - - 1 1")
    c = _claim("no_flight", Ref(piece="K", side=chess.BLACK))
    assert R.judge_no_flight(c, mated, None).status == "true"
    before = chess.Board("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1")  # «no luft» said before Rd8: not this board
    assert R.judge_no_flight(c, before, None).status == "undecided"
    free = chess.Board("6k1/5pp1/7p/8/8/8/5PPP/3R2K1 b - - 0 1")
    v = R.judge_no_flight(c, free, None)
    assert v.status == "false" and "h7" in v.truth


def test_confined_walks_the_king_with_the_board_standing():
    b = chess.Board("6k1/3R1pp1/7p/8/8/8/5PPP/6K1 b - - 1 1")  # after 1.Rd7 of mate1-no
    c = _claim("confined", Ref(piece="K", side=chess.BLACK), kind="ranks", count=2)
    v = R.judge_confined(c, b, None)
    assert v.status == "false" and "Kh7 and then Kg6" in v.truth
    shut = chess.Board("6k1/R7/8/8/8/8/5PPP/6K1 b - - 1 1")  # the rook on the 7th: the king stays on the 8th
    assert R.judge_confined(_claim("confined", Ref(piece="K", side=chess.BLACK), kind="ranks", count=1), shut, None).status == "true"
    assert R.judge_confined(_claim("confined", Ref(piece="K", side=chess.BLACK), kind="cut_rank", count=7), shut, None).status == "true"


def test_checks_along_a_file():
    b = chess.Board("8/2K5/8/4k3/3R4/8/1P6/r7 b - - 0 1")  # Lucena after Kc7: no d-file check for Black
    c = _claim("checks_along", Ref(piece="R", side=chess.BLACK), kind="file:d")
    v = R.judge_checks_along(c, b, None)
    assert v.status == "false" and "Rc1+" in v.truth
    b = chess.Board("3K4/8/8/4k3/8/8/1P6/r7 b - - 0 1")  # the king on d8: Rd1+ is a d-file check
    assert R.judge_checks_along(c, b, None).status == "true"


def test_only_move_counts_legal_moves_and_blocks():
    b = chess.Board("1r4k1/8/8/8/8/8/3Q1PPP/1r4K1 w - - 0 1")
    q = _claim("only_move", Ref(piece="Q"), kind="block")
    assert R.judge_only_move(q, b, None).status == "true"
    m = _claim("only_move", None, kind="block", move=MoveRef(san="Qd1", piece="Q", to="d1"))
    v = R.judge_only_move(m, b, None)
    assert v.status == "false" and "Qc1" in v.truth
    a = _claim("only_move", None, kind="any", move=MoveRef(san="Kh1", piece="K", to="h1"))
    assert R.judge_only_move(a, chess.Board(), None).status == "undecided"  # not a move of this board
    only = _claim("only_move", None, kind="any", move=MoveRef(san="e4", piece="P", to="e4"))
    v = R.judge_only_move(only, chess.Board(), None)
    assert v.status == "false" and "and 15 more" in v.truth
    forced = chess.Board("6k1/8/8/8/8/8/6PP/r5K1 w - - 0 1")  # in check from a1: Kf2 is the only legal move
    king = _claim("only_move", None, kind="any", move=MoveRef(san="Kf2", piece="K", to="f2"))
    assert R.judge_only_move(king, forced, None).status == "true"


def test_occupied_and_free():
    start = chess.Board()
    assert R.judge_occupied(_claim("occupied", None, [Ref(sq="e5")]), start, None).status == "false"
    assert R.judge_occupied(_claim("occupied", None, [Ref(sq="f7", piece="P"), Ref(sq="g7")]), start, None).status == "true"
    assert R.judge_occupied(_claim("occupied", None, [Ref(sq="e2")], neg=True), start, None).status == "false"
    assert R.judge_occupied(_claim("occupied", None, [Ref(sq="g1", piece="B")]), start, None).status == "false"


def test_the_blocker_must_stand_next_to_the_king():
    b = chess.Board("k7/8/8/8/8/8/5PPP/2Q3K1 b - - 0 1")
    c = _claim("no_flight", Ref(piece="K", owner="own"), [Ref(piece="Q")], kind="blocker")
    v = R.judge_no_flight(c, b, None)
    assert v.status == "false" and "queen on c1" in v.truth
    near = chess.Board("k7/8/8/8/8/8/5PPP/5QK1 b - - 0 1")
    assert R.judge_no_flight(c, near, None).status == "true"
    gone = chess.Board("k7/8/8/8/8/8/5PPP/6K1 b - - 0 1")
    assert R.judge_no_flight(c, gone, None).status == "undecided"


def test_extract_latency():
    import time

    sents = [s for case in CASES["positive"] + CASES["negative"] for s in case.get("sentences") or [case["sentence"]]]
    times = []
    for _ in range(5):
        for s in sents:
            t = time.perf_counter()
            R.extract(s, {})
            times.append((time.perf_counter() - t) * 1000)
    times.sort()
    assert times[int(0.99 * (len(times) - 1))] < 2.0  # the 0.5 ms bound is measured on the corpus (merge note)


# ── _retreat_square_issues: every square where the chased piece is lost (d1-why) ─────────────────────────────────
def test_d1_why_names_every_square_where_the_bishop_is_lost():
    from src.answer_check_rules import _retreat_square_issues

    ctx = ac.CheckContext.from_fens(["r2qk2r/ppp2ppp/2np1n2/4p3/2b1P3/2N2N2/PPP2PPP/R1BQK2R w KQkq - 0 8"],
                                    question="Почему я не могу рокироваться?")
    s = "Заметь: прогнать слона с c4 недостаточно — он спокойно отойдёт на a6, b5, d3 или e2 и всё равно будет бить по f1."
    issues = _retreat_square_issues(s.lower(), ctx)
    assert len(issues) == 1
    issue = issues[0]
    assert "no retreat to b5, d3, e2" in issue and "Nxb5" in issue and "cxd3" in issue and "Nxe2" in issue
    assert "only a6 is a real retreat" in issue


def test_retreat_judged_on_every_chase_when_none_leaves_all_the_squares_open():
    from src.answer_check_rules import _retreat_square_issues

    # «a6 или d3» — after d3 the d3 square is no retreat, after b3/Nd2 both are: those chases are the main ones
    ctx = ac.CheckContext.from_fens(["r2qk2r/ppp2ppp/2np1n2/4p3/2b1P3/2N2N2/PPP2PPP/R1BQK2R w KQkq - 0 8"])
    issues = _retreat_square_issues("прогнать слона мало — он уйдёт на a6 или d3.", ctx)
    assert issues and "no retreat to d3" in issues[0] and "a6 is a real retreat" in issues[0]
