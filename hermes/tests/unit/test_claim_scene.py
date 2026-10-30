"""The position resolver (WP-B, plan 30.10 §4): a claim's textual Pos → the boards it can mean, and what a sentence
leaves for the next one. The verdicts on these boards are in test_claim_judge.py (judge_cases.json)."""
from __future__ import annotations

import chess
import pytest

from src import claim_judge, claim_scene
from src.answer_check import CheckContext
from src.claim_types import Claim, MoveRef, Pos, Ref, parse_san_token

WINAWER = "rnbqk1nr/ppp2ppp/4p3/3p4/1b1PP3/2N5/PPP2PPP/R1BQKBNR w KQkq - 2 4"
NAJDORF = "rnbqkb1r/1p2pppp/p2p1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 0 6"
WC_LINE = '[FEN "3k4/q4R2/4P3/5P1N/7K/8/8/8 b - - 0 135"] 135... Qg1 136. Ng7'
WC_FINAL = "3k4/5RN1/4P3/5P2/7K/8/8/6q1 b - - 2 136"


def ctx_for(fen, shown=None, game=None, question="", lines=(), student=None) -> CheckContext:
    all_lines = list(lines) + ([" ".join(game)] if game else [])
    ctx = CheckContext.from_fens([fen, shown], lines=all_lines, question=question, student_color=student)
    if game is not None:
        ctx.game_moves = list(game) or None
    return ctx


def claim(rel="attack", subj=None, objs=(), pos=Pos(), **kw) -> Claim:
    return Claim(rel=rel, subj=subj, objs=tuple(objs), pos=pos, **kw)


def mv(tok, **kw) -> MoveRef:
    m = parse_san_token(tok)
    return MoveRef(**{**m.to_dict(), **kw}) if kw else m


def fen_of(board: chess.Board) -> str:
    return board.board_fen()


# ── moves told in the text → moves on a board ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ref, uci", [
    (mv("e5"), "e4e5"), (mv("Nf3"), "g1f3"), (MoveRef(piece="N", to="f3"), "g1f3"), (MoveRef(piece="P", frm="e4", to="e5"), "e4e5"),
    (MoveRef(san="Кf3"), "g1f3"), (MoveRef(san="e4-e5"), "e4e5"),
])
def test_to_move(ref, uci):
    b = chess.Board("rnbqkbnr/pppp1ppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    assert claim_scene.to_move(b, ref).uci() == uci


def test_to_move_castles_and_ambiguity():
    b = chess.Board("r3k2r/8/8/8/8/2N3N1/8/R3K2R w KQkq - 0 1")
    assert claim_scene.to_move(b, MoveRef(castle="short")).uci() == "e1g1"
    assert claim_scene.to_move(b, MoveRef(castle="long")).uci() == "e1c1"
    assert claim_scene.to_move(b, MoveRef(piece="N", to="e4")) is None  # two knights reach e4, none named
    assert claim_scene.to_move(b, MoveRef(piece="N", frm="c3", to="e4")).uci() == "c3e4"
    assert claim_scene.to_move(b, MoveRef(piece="N", to="e4", capture=True)) is None  # e4 is empty


# ── boards for each Pos ─────────────────────────────────────────────────────────────────────────────────────────
def test_now_is_the_board_now():
    ctx = ctx_for(WINAWER)
    bs = claim_scene.boards_for(claim(subj=Ref(sq="b4", piece="B"), objs=[Ref(sq="c3", piece="N")]), ctx, {})
    assert bs.primary is ctx.current and bs.where == "on the board now" and bs.shown is None


def test_after_a_named_move():
    bs = claim_scene.boards_for(claim(pos=Pos(at="after", moves=(mv("e5"),))), ctx_for(WINAWER), {})
    assert bs.where == "after 4.e5"
    assert bs.primary.piece_at(chess.E5) == chess.Piece(chess.PAWN, chess.WHITE)
    assert claim_scene.last_move(bs.primary).uci() == "e4e5"


def test_or_gives_an_alternative_branch():
    pos = Pos(at="after", moves=(mv("Nf3"),), alts=(Pos(at="after", moves=(mv("Nc3"),)),))
    bs = claim_scene.boards_for(claim(pos=pos), ctx_for("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"), {})
    assert bs.primary.piece_at(chess.F3) is not None
    assert any(b.piece_at(chess.C3) == chess.Piece(chess.KNIGHT, chess.WHITE) for b in bs.alternatives)


def test_bare_pawn_move_for_both_sides_unless_the_move_is_asked():
    fen = "4k3/p7/8/1p6/8/P7/8/4K3 w - - 0 1"
    pos = Pos(at="after", moves=(mv("a4"),))
    bs = claim_scene.boards_for(claim(pos=pos), ctx_for(fen), {})
    assert bs.primary.piece_at(chess.A4) == chess.Piece(chess.PAWN, chess.WHITE)
    fen_b = "4k3/p7/8/8/8/8/P7/4K3 b - - 0 1"  # Black to move: a7-a5 now, a2-a4 as the other reading
    bs = claim_scene.boards_for(claim(pos=Pos(at="after", moves=(mv("a5"),))), ctx_for(fen_b), {})
    assert bs.primary.piece_at(chess.A5) == chess.Piece(chess.PAWN, chess.BLACK)
    pos4 = Pos(at="after", moves=(mv("a4"),))
    bs = claim_scene.boards_for(claim(pos=pos4), ctx_for("4k3/p7/8/p7/8/8/P7/4K3 b - - 0 1"), {})
    # a5-a4 (Black) and a2-a4 (White) are both legal: both readings
    assert {b.piece_at(chess.A4).color for b in (bs.primary,) + bs.alternatives if b.piece_at(chess.A4)} == {True, False}
    bs = claim_scene.boards_for(claim(pos=pos4), ctx_for("4k3/p7/8/p7/8/8/P7/4K3 b - - 0 1",
                                                         question="Какой здесь лучший ход?"), {})
    assert not any(b.piece_at(chess.A4) == chess.Piece(chess.PAWN, chess.WHITE) for b in bs.alternatives)


def test_a_move_told_again_in_words_is_one_move():
    game = ["e4", "c5", "Nf3", "d6", "Bc4", "e6", "O-O", "Nf6", "d3", "h6", "h3", "Nc6"]
    ctx = ctx_for("r1bqkb1r/pp3pp1/2nppn1p/2p5/2B1P3/3P1N1P/PPP2PP1/RNBQ1RK1 w kq - 1 7", game=game)
    pos = Pos(at="after", moves=(mv("h3", told=True), mv("Nc6", told=True), MoveRef(piece="N", frm="b8", to="c6", told=True)))
    bs = claim_scene.boards_for(claim(pos=pos), ctx, {})
    assert fen_of(bs.primary) == fen_of(ctx.current) and bs.where == "right after 6...Nc6 was played"


def test_a_move_already_on_the_board_is_skipped():
    ctx = ctx_for("rnb1kbnr/pppp1ppp/1q6/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3")
    bs = claim_scene.boards_for(claim(pos=Pos(at="after", moves=(mv("Qb6"),))), ctx, {})
    assert bs.primary is ctx.current


def test_a_move_the_game_made_is_the_board_right_after_it():
    ctx = ctx_for("rnbqkb1r/pppppppp/5n2/8/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 1 2", game=["d4", "Nf6"])
    bs = claim_scene.boards_for(claim(pos=Pos(at="after", moves=(mv("d4", told=True),))), ctx, {})
    assert bs.where == "right after 1.d4 was played" and bs.primary.piece_at(chess.F6) is None


def test_a_numbered_move_of_a_line_the_turn_has():
    ctx = ctx_for(chess.STARTING_FEN, shown=WC_FINAL, lines=[WC_LINE])
    pos = Pos(at="after", moves=(mv("135...Qg1", told=True),), tense="past")
    bs = claim_scene.boards_for(claim(pos=pos), ctx, {})
    assert bs.where == "right after 135...Qg1 was played"
    assert bs.primary.piece_at(chess.H5) == chess.Piece(chess.KNIGHT, chess.WHITE)  # not the final board
    assert claim_scene.boards_for(claim(pos=Pos(at="after", moves=(mv("12...Nf6"),))), ctx_for(WINAWER), {}) is None


def test_another_move_at_a_numbered_point_of_the_game():
    game = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Nd4 4. Nxe5 Qg5 5. Nxf7 Qxg2 6. Rf1 Qxe4+ 7. Be2 Nf3#"
    ctx = ctx_for("r1b1kbnr/pppp1Npp/8/8/4q3/5n2/PPPPBP1P/RNBQKR2 w Qkq - 2 8", lines=[game])
    bs = claim_scene.boards_for(claim(pos=Pos(at="after", moves=(MoveRef(castle="short", number="5."),))), ctx, {})
    assert bs.where.startswith("after 5.O-O (instead of 5.Nxf7)")
    assert bs.primary.piece_at(chess.G1) == chess.Piece(chess.KING, chess.WHITE)


def test_the_idea_of_the_side_not_to_move_is_played_after_a_null_move():
    bs = claim_scene.boards_for(claim(pos=Pos(at="after", moves=(mv("Bg4"),))), ctx_for(NAJDORF), {})
    assert bs.where == "after the idea 6...Bg4" and bs.primary.turn == chess.WHITE


def test_unplayable_and_skipped_positions_have_no_board():
    ctx = ctx_for(WINAWER)
    assert claim_scene.boards_for(claim(pos=Pos(at="after", moves=(mv("Ne5"),))), ctx, {}) is None
    assert claim_scene.boards_for(claim(pos=Pos(at="skip", skip_reason="if")), ctx, {}) is None
    assert claim_scene.boards_for(claim(question="yesno"), ctx, {}) is None
    assert claim_scene.boards_for(claim(pos=Pos(at="then")), ctx, {}) is None  # nothing before it


def test_the_past_with_no_history_is_any_position():
    bs = claim_scene.boards_for(claim(pos=Pos(tense="past")), ctx_for(WINAWER), {})
    assert bs is claim_scene.ANY_POSITION and bs.primary is None


def test_the_past_tense_adds_the_last_two_positions_of_the_game():
    ctx = ctx_for("rnbqkb1r/pppppppp/5n2/8/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 1 2", game=["d4", "Nf6"])
    bs = claim_scene.boards_for(claim(pos=Pos(tense="past")), ctx, {})
    fens = {fen_of(b) for b in bs.alternatives}
    assert chess.Board().board_fen() in fens and "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR" in fens


def test_the_shown_board_is_an_alternative_and_must_be_judgeable():
    shown = "rnbqkbnr/pp1ppppp/2p5/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
    ctx = ctx_for(WINAWER, shown=shown)
    bs = claim_scene.boards_for(claim(), ctx, {})
    assert fen_of(bs.shown) == chess.Board(shown).board_fen()
    assert any(b is bs.shown for b in bs.alternatives)


def test_the_default_start_position_gives_way_to_the_board_shown():
    shown = "r2q1rk1/ppp2ppp/2npbn2/2b1p1B1/4P3/1BNP1N2/PPP2PPP/R2Q1RK1 b - - 0 1"
    bs = claim_scene.boards_for(claim(), ctx_for(chess.STARTING_FEN, shown=shown), {})
    assert bs.where == "on the board shown" and fen_of(bs.primary) == chess.Board(shown).board_fen()
    # with no board shown and no line from the start, a claim is about a diagram the turn does not have
    assert claim_scene.boards_for(claim(), ctx_for(chess.STARTING_FEN), {}) is None
    line = Pos(at="after", moves=(mv("1.e4"), mv("e5"), mv("2.Nf3")))
    assert claim_scene.boards_for(claim(pos=line), ctx_for(chess.STARTING_FEN), {}) is not None


def test_solution_lines_and_the_puzzle_fallback():
    fen = "3Rn1k1/1b3ppp/p1p5/4q3/2B1n3/P6P/2Q2PP1/6K1 w - - 0 1"
    ctx = ctx_for(fen, question="Какой здесь первый ход?")
    ctx.solution_lines = [["f4", "Qd6"]]
    bs = claim_scene.boards_for(claim(), ctx, {})
    assert len(bs.alternatives) == 2  # after f4, after f4 Qd6
    ctx = ctx_for(fen, question="Какой здесь первый ход?")
    bs = claim_scene.boards_for(claim(), ctx, {})
    assert len(bs.alternatives) == ctx.current.legal_moves.count()  # unknown solution: every move
    assert claim_scene.boards_for(claim(), ctx_for(fen, question="Опиши позицию"), {}).alternatives == ()


def test_from_square_subject_adds_that_pieces_moves():
    fen = "r4k2/ppq3pp/2p1Qn2/6N1/3P1P1N/8/PPPn2PP/R5K1 w - - 0 1"
    ctx = ctx_for(fen)
    subj = Ref(sq="g5", piece="N", from_sq=True)
    bs = claim_scene.boards_for(claim(subj=subj), ctx, {})
    moves = [m for m in ctx.current.legal_moves if m.from_square == chess.G5]
    assert len(bs.alternatives) == len(moves) > 0
    assert all(claim_scene.last_move(b).from_square == chess.G5 for b in bs.alternatives)


def test_the_implicit_move_is_never_the_primary_board():
    fen = "rnbqkb1r/pp2pp1p/3p1np1/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 0 6"
    ctx = ctx_for(fen)
    bs = claim_scene.boards_for(claim(rel="aim", subj=Ref(sq="g7", piece="B"), objs=[Ref(sq="c3", piece="N")]), ctx, {})
    assert bs.primary is ctx.current
    assert any(b.piece_at(chess.G7) == chess.Piece(chess.BISHOP, chess.BLACK) for b in bs.alternatives)


def test_the_board_before_a_capture_the_claim_names():
    fen = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
    c = claim(rel="defend", subj=Ref(piece="K"), objs=[Ref(sq="f7", piece="P")], pos=Pos(at="after", moves=(mv("Qxf7#"),)))
    bs = claim_scene.boards_for(c, ctx_for(fen), {})
    assert any(b.piece_at(chess.F7) == chess.Piece(chess.PAWN, chess.BLACK) for b in bs.alternatives)
    other = claim(rel="attack", subj=Ref(sq="f7", piece="Q"), objs=[Ref(sq="e8", piece="K")], pos=Pos(at="after", moves=(mv("Qxf7#"),)))
    assert claim_judge.decide(other, claim_scene.boards_for(other, ctx_for(fen), {}), ctx_for(fen)).status == "true"


# ── what a sentence leaves for the next one ────────────────────────────────────────────────────────────────────
def test_remember_then_and_its_age():
    fen = "6k1/5pp1/7p/8/8/8/5PPP/3R2K1 w - - 0 1"
    ctx = ctx_for(fen)
    state: dict = {}
    told = claim(rel="gives_check", pos=Pos(at="after", moves=(mv("Rd8+"),)))
    claim_scene.remember("Rd8+ — шах.", [told], ctx, state)
    then = state[claim_scene.THEN_KEY]
    assert all(isinstance(x, (str, int)) for x in then)  # immutable: a shallow copy of the state is a snapshot
    nxt = claim(subj=Ref(sq="d8", piece="R"), objs=[Ref(sq="g8", piece="K")], pos=Pos(at="then"))
    bs = claim_scene.boards_for(nxt, ctx, state)
    assert bs is not None and bs.primary.piece_at(chess.D8) == chess.Piece(chess.ROOK, chess.WHITE)
    assert claim_scene.last_move(bs.primary).uci() == "d1d8"
    for _ in range(claim_scene.THEN_MAX_AGE):
        claim_scene.remember("Без ходов.", [], ctx, state)
        assert claim_scene.THEN_KEY in state
    claim_scene.remember("Ещё одно.", [], ctx, state)
    assert claim_scene.THEN_KEY not in state


def test_a_cut_sentence_leaves_nothing_for_the_next(monkeypatch):
    """check_sentence restores relation_state when the sentence is cut: its told line is not «then» for the next."""
    from src import answer_check, answer_check_relations as acr, config

    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    fen = "6k1/5pp1/7p/8/8/8/5PPP/3R2K1 w - - 0 1"
    ctx = CheckContext.from_fens([fen])
    wrong = claim(subj=Ref(sq="d8", piece="R"), objs=[Ref(sq="f7", piece="P")], pos=Pos(at="after", moves=(mv("Rd8+"),)))
    monkeypatch.setattr(acr, "extract_claims", lambda text, c, state: [wrong])
    issues = answer_check.check_sentence("После Rd8+ ладья бьёт пешку f7.", ctx)
    assert any("after 1.Rd8+" in i and "not Black's pawn on f7" in i for i in issues), issues
    assert claim_scene.THEN_KEY not in ctx.relation_state


def test_relation_issues_end_to_end(monkeypatch):
    """The real resolver and judge behind relation_issues: the issue names the board, then the truth."""
    from src import answer_check_relations as acr, config

    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    ctx = CheckContext.from_fens([WINAWER])
    c = claim(subj=Ref(sq="e5", piece="P"), objs=[Ref(sq="g8", piece="N")], pos=Pos(at="after", moves=(mv("e5"),)))
    monkeypatch.setattr(acr, "extract_claims", lambda text, x, state: [c])
    issues = acr.relation_issues("e4-e5 с ударом по коню g8", ctx, [])
    assert issues == ["after 4.e5: White's pawn on e5 attacks d6 and f6 (no enemy piece) — not Black's knight on g8"]
    assert ctx.relation_stats["errors"] == 0


def test_resolution_is_memoised_within_a_sentence():
    ctx = ctx_for(WINAWER)
    c = claim(pos=Pos(at="after", moves=(mv("e5"),)))
    a, b = claim_scene.boards_for(c, ctx, {}), claim_scene.boards_for(c, ctx, {})
    assert a.primary is b.primary
