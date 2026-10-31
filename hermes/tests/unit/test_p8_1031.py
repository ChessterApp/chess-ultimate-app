"""Plan 31.10, package P8 (prevention): the facts the model is given are true, and they carry the truth the 29.10
answers contradicted.

  * forks (C1): told only with a proof — the engine's lines of the turn (within 1.0 of the best) or, without them,
    every reply played out by exchange count; a mate on the board is the point, not a fork beside it;
  * piece safety (C6): an attacked piece of the side to move gets the squares where it is safe by exchange count;
  * attack balance (F5): attacked as often as defended — the moves that add one more attacker (and do not hang the
    piece brought) and the moves that defend it once more;
  * the game's facts (F1, F3, F4): material by units, the captures that win material with the exchange counted
    (promotions valued as the piece made), the replies to a check by kind;
  * opening ideas (content/openings/ideas.yaml) next to the book's name;
  * the resign block: the final evaluation and the rule not to justify the resignation.

COACH_TURN_FACTS=0 gives back the prompts of before. The true controls are tests/fixtures/detect1031/negatives/P8.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import chess
import pytest

from src import config, position_facts as pf, turn_facts
from src.board_math import move_loss, safe_squares
from src.turn_facts import Fact

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "detect1031"
CONTROLS = json.loads((FIX / "negatives" / "P8.json").read_text(encoding="utf-8"))["controls"]

MATE2_NO = "r1bq1b1r/ppp3pp/2n1k3/3np3/2B5/5Q2/PPPP1PPP/RNB1K2R w KQ - 2 8"   # 8.Nc3 best; Qxd5+? Qxd5
G1_RESIGN = "rnbqkb1r/pppppppp/5n2/4P3/8/8/PPPP1PPP/RNBQKBNR b KQkq - 0 2"   # 1.e4 Nf6 2.e5, Black resigned
ST2_2 = "r1bqkbnr/pppp1ppp/2n5/4P3/8/5N2/PPP1PPPP/RNBQKB1R b KQkq - 2 3"     # 1.d4 e5 2.dxe5 Nc6 3.Nf3
ST2_4 = "r1bqkb1r/pppp1ppp/2n2P2/8/8/5N2/PPP1PPPP/RNBQKB1R b KQkq - 0 4"     # … 3...Nf6 4.exf6
ST2_8 = "r1bRk2r/ppp2ppp/2np4/8/8/5N2/PPP1PPPP/RNBQKB1R b KQkq - 0 6"       # … 6.exd8=R+
SLAV = "rnbqkbnr/pp2pppp/2p5/3p4/2PP4/8/PP2PPPP/RNBQKBNR w KQkq - 0 3"
NAJDORF = "rnbqkb1r/1p2pppp/p2p1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 0 6"

# The engine's lines of the mate2-no turn (replay1031: Nc3 +1.06, a4 −2.69, Qg3 −2.86), in analyze_* form.
MATE2_NO_LINES = [{"pv": "b1c3 c6b4", "score": 1.06, "mate_in": None},
                  {"pv": "a2a4", "score": -2.69, "mate_in": None},
                  {"pv": "f3g3", "score": -2.86, "mate_in": None}]


@pytest.fixture
def facts_on(monkeypatch):
    monkeypatch.setattr(config, "COACH_TURN_FACTS", True)


@pytest.fixture
def facts_off(monkeypatch):
    monkeypatch.setattr(config, "COACH_TURN_FACTS", False)


def _sans(facts: list[str]) -> list[str]:
    return [m["san"] for f in facts if (m := re.search(r"available now: (?P<san>\S+) attacks", f))]


def _corpus_boards() -> list:
    seen, out = set(), []
    for name in ("corpus_positions.json", "game_positions.json"):
        for x in json.loads((FIX / name).read_text(encoding="utf-8"))["positions"]:
            b = chess.Board(x["fen"])
            if b.is_valid() and b.epd() not in seen:
                seen.add(b.epd())
                out.append(b)
    return out


CORPUS = _corpus_boards()


# ── C1 forks ────────────────────────────────────────────────────────────────────────────────────────────────────

def test_mate2_no_fork_is_no_longer_told(facts_on):
    board = chess.Board(MATE2_NO)
    assert "Qxd5+" not in _sans(pf.fork_facts(board))                       # board only: 8...Qxd5 takes it back
    assert "Qxd5+" not in _sans(pf.fork_facts(board, lines=MATE2_NO_LINES))  # not among the engine's lines
    assert "Bxd5+" not in _sans(pf.static_facts(board, MATE2_NO_LINES))


def test_the_old_fork_comes_back_with_the_switch_off(facts_off):
    assert "Qxd5+" in _sans(pf.fork_facts(chess.Board(MATE2_NO)))


def test_engine_lines_keep_a_fork_within_one_pawn_of_the_best(facts_on):
    board = chess.Board("r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1")
    assert _sans(pf.fork_facts(board, lines=[{"pv": "d5c7 e8d7 c7a8", "score": 4.8}])) == ["Nc7+"]
    assert _sans(pf.fork_facts(board, lines=[{"pv": "e1d2", "score": 5.0}, {"pv": "d5c7", "score": 4.1}])) == ["Nc7+"]
    assert pf.fork_facts(board, lines=[{"pv": "e1d2", "score": 5.0}, {"pv": "d5c7", "score": 3.5}]) == []
    assert pf.fork_facts(board, lines=[{"pv": "e1d2", "score": 5.0}]) == []


def test_mates_count_as_the_best_line(facts_on):
    board = chess.Board("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4")
    assert _sans(pf.fork_facts(board, lines=[{"pv": "h5f7", "score": None, "mate_in": 1}])) == ["Qxf7#"]
    assert _sans(pf.fork_facts(board)) == ["Qxf7#"]


@pytest.mark.parametrize("control", [c for c in CONTROLS if c["fact_kind"] == "fork"], ids=lambda c: c["id"])
def test_fork_controls(control, facts_on):
    told = _sans(pf.fork_facts(chess.Board(control["fen"]), limit=10))
    typed = [f.data["san"] for f in turn_facts.facts_for_board(chess.Board(control["fen"]), None, ("fork",))]
    if control.get("keep"):
        assert control["keep"] in told, control["why"]
    if control.get("drop"):
        assert control["drop"] not in told and control["drop"] not in typed, control["why"]


def test_the_engine_note_drops_the_poisoned_fork(facts_on):
    from src.voice_engine_note import _facts

    board = chess.Board(MATE2_NO)
    told = _facts(board, MATE2_NO_LINES[0], None, lines=MATE2_NO_LINES)
    assert not any("fork is available now: Qxd5+" in f for f in told)
    # eval_prevent's audit path gives the top line only: a fork must be that move
    assert not any("fork is available now" in f for f in _facts(board, MATE2_NO_LINES[0], None))


def test_a_kept_fork_without_engine_wins_against_every_reply(facts_on):
    """The exchange-count proof of every board-only fork on the corpus, re-checked independently: against every
    legal reply the side to move nets at least FORK_MIN_GAIN by one capture (or the fork is the start of a mate)."""
    for board in CORPUS:
        for move, targets, after, source in pf.vetted_forks(board):
            assert source == "see"
            if after.is_checkmate() or pf.starts_mate_in_two(board, move):
                continue
            assert pf.fork_holds(board, move, targets), board.fen()
            assert not pf.has_mate_in_two_by_checks(board, skip=move), board.fen()


# ── C6 safety, F5 balance ──────────────────────────────────────────────────────────────────────────────────────

# The engine's lines of the g1-resign board (Stockfish, 1.5 s: 2...Nd5 −0.6, 2...Ng8 −1.1, 2...Ne4 −1.5 from White's
# side flipped to Black's), in analyze_* form for the side to move.
G1_LINES = [{"pv": "f6d5 c2c4", "score": -0.55}, {"pv": "f6g8 d2d4", "score": -1.05},
            {"pv": "f6e4 d2d3", "score": -1.45}]


def test_g1_resign_knight_has_safe_squares(facts_on):
    board = chess.Board(G1_RESIGN)
    facts = turn_facts.facts_for_board(board, G1_LINES, ("piece_safety",))
    assert len(facts) == 1 and facts[0].source == "see" and facts[0].proven
    assert facts[0].data["sq"] == "f6" and set(facts[0].data["safe"]) == {"d5", "e4", "g8"}
    assert re.search(r"safe squares?.{0,40}d5|d5.{0,40}safe squares", facts[0].text)


def test_a_safe_square_is_told_only_when_the_engine_line_starts_with_it(facts_on):
    board = chess.Board(G1_RESIGN)
    assert pf.safety_items(board) == []   # no lines: a safe square may still be a bad move (Bd3 after 3...a6)
    items = pf.safety_items(board, [{"pv": "f6d5", "score": -0.5}, {"pv": "f6g4", "score": -0.6},
                                    {"pv": "f6e4", "score": -2.0}])
    assert items[0]["safe"] == ["d5"]          # g4 is not safe (Qxg4), e4 is 1.5 below the best line
    assert pf.safety_items(board, [{"pv": "d7d6", "score": 0.3}]) == []


def test_safety_is_only_for_the_side_to_move_and_not_in_check():
    assert pf.safety_items(chess.Board(G1_RESIGN.replace(" b ", " w ")), G1_LINES) == []
    assert pf.safety_items(chess.Board(ST2_8), []) == []   # in check: the check replies come first


def test_a_trapped_piece_is_told_as_such(facts_on):
    board = chess.Board("r3k3/B1p5/1p6/8/8/8/8/4K3 w - - 0 1")   # the a7 bishop: Ra8 hits it, Bb8 Rxb8, Bxb6 cxb6
    items = pf.safety_items(board)
    assert items and items[0]["sq"] == "a7" and items[0]["safe"] == [] and items[0]["trapped"]
    assert "no safe square" in pf.safety_text(items[0])


def _all_lines(board):
    return [{"pv": m.uci(), "score": 0.0} for m in board.legal_moves]


def test_safety_facts_agree_with_board_math_on_the_corpus():
    n = 0
    for board in CORPUS:
        for item in pf.safety_items(board, _all_lines(board)):
            sq = chess.parse_square(item["sq"])
            assert set(item["safe"]) <= {chess.square_name(s) for s in safe_squares(board, sq)}
            if item["trapped"]:
                assert not item["safe"]
                for mv in board.legal_moves:
                    if mv.from_square == sq:
                        assert move_loss(board, mv) > 0
            for name in item["safe"]:
                for mv in board.legal_moves:
                    if mv.from_square == sq and chess.square_name(mv.to_square) == name:
                        assert move_loss(board, mv) == 0
            n += 1
    assert n > 10


def test_st2_2_one_more_attacker(facts_on):
    board = chess.Board(ST2_2)
    facts = turn_facts.facts_for_board(board, None, ("attack_balance",))
    assert len(facts) == 1
    data = facts[0].data
    assert data["sq"] == "e5" and data["attackers"] == ["c6"] and data["defenders"] == ["f3"]
    assert "Qe7" in data["adders"] and "Bf4" in data["guards"]
    assert "one more attacker" in facts[0].text and facts[0].source == "see"


def test_balance_adders_hold_on_the_corpus():
    """Every listed adder brings one more attacker, does not hang the piece brought, and makes the exchange win;
    every listed guard brings one more defender and does not hang."""
    from src.board_math import _as_side

    n = 0
    for board in CORPUS:
        for item in pf.balance_items(board):
            sq = chess.parse_square(item["sq"])
            before = len(board.attackers(board.turn, sq))
            assert before == len(board.attackers(not board.turn, sq))
            for san in item["adders"]:
                mv = board.parse_san(san)
                after = board.copy(stack=False)
                after.push(mv)
                assert len(after.attackers(board.turn, sq)) > before and move_loss(board, mv) == 0
                assert (pf.exchange_gain(after, sq) or 0) > 0
            owner = _as_side(board, not board.turn)
            for san in item["guards"]:
                mv = owner.parse_san(san)
                after = owner.copy(stack=False)
                after.push(mv)
                assert len(after.attackers(owner.turn, sq)) > len(owner.attackers(owner.turn, sq))
                assert move_loss(owner, mv) == 0
            n += 1
    assert n > 5


# ── F1, F3, F4 ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_st2_4_the_pawn_is_taken_back():
    items = pf.capture_items(chess.Board(ST2_4))
    assert {it["san"] for it in items} == {"gxf6", "Qxf6"} and all(it["net"] == 1 for it in items)


def test_a_capture_that_promotes_is_valued_as_the_piece_made():
    board = chess.Board("r1bqk2r/ppppPppp/2n5/8/8/5N2/PPP1PPPP/RNBQKB1R w KQkq - 0 6")
    mv = board.parse_san("exd8=Q+")
    assert pf.capture_net(board, mv) == 9 + 8 - 9   # the queen d8 and a new queen, which Kxd8 or Nxd8 takes
    assert pf.capture_net(board, board.parse_san("exd8=R+")) == 9 + 4 - 5


def test_st2_8_check_replies_by_kind():
    item = pf.check_reply_item(chess.Board(ST2_8))
    assert item["take"] == ["Kxd8", "Nxd8"] and item["king"] == ["Ke7"] and item["block"] == []
    text = pf.check_reply_text(item, chess.Board(ST2_8))
    assert "the white rook d8" in text and "replies to the check" in text and "blocks: none" in text


def test_material_by_units():
    m = pf.material_item(chess.Board(ST2_8))
    text = pf.material_text(m)
    assert "White +20" in text and "a queen, a rook, a bishop and a knight more" in text
    assert "level" in pf.material_text(pf.material_item(chess.Board()))
    mixed = pf.material_text(pf.material_item(chess.Board(MATE2_NO)))
    assert "Black +2" in mixed and "White has a pawn more" in mixed and "Black has a knight more" in mixed


def test_check_replies_agree_with_python_chess_on_the_corpus():
    for board in CORPUS:
        item = pf.check_reply_item(board)
        if item is None:
            assert not board.is_check()
            continue
        told = item["take"] + item["king"] + item["block"]
        assert sorted(told) == sorted(board.san(m) for m in board.legal_moves)


# ── the typed contract ─────────────────────────────────────────────────────────────────────────────────────────

def test_every_outcome_fact_on_the_corpus_is_proven(facts_on):
    kinds = set()
    for board in CORPUS:
        for f in turn_facts.facts_for_board(board) + turn_facts.facts_for_board(board, _all_lines(board)):
            assert isinstance(f, Fact) and f.proven, f
            kinds.add(f.kind)
    assert {"fork", "piece_safety", "attack_balance", "recapture", "check_replies", "material"} <= kinds


def test_collect_obeys_the_switch_and_remembers_the_board(facts_on, monkeypatch):
    board = chess.Board(G1_RESIGN)
    got = turn_facts.collect(board)
    assert got and turn_facts.recent(board.fen()) == got and turn_facts.recent(board.fen(), engine=True) is None
    monkeypatch.setattr(config, "COACH_TURN_FACTS", False)
    assert turn_facts.collect(board) == []


def test_collect_never_raises(facts_on, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(turn_facts, "facts_for_board", boom)
    assert turn_facts.collect(chess.Board(G1_RESIGN)) == []


def test_provider_time_is_small_on_the_corpus(facts_on):
    import time

    times = []
    for board in CORPUS:
        t = time.perf_counter()
        turn_facts.facts_for_board(board, None, ("check_replies", "piece_safety", "attack_balance", "recapture",
                                                 "material"))
        times.append((time.perf_counter() - t) * 1000)
    times.sort()
    assert times[len(times) // 2] < 5, times[len(times) // 2]   # median; the replay measures the p99 (eval_prevent d)


# ── the prompt blocks ──────────────────────────────────────────────────────────────────────────────────────────

def test_board_facts_block_carries_the_new_facts(facts_on):
    from src.prompt_builder import board_facts_block

    st2 = board_facts_block(ST2_2)
    assert "one more attacker" in st2 and "Qe7" in st2 and "material on the board" in st2
    assert "safe squares" not in board_facts_block(G1_RESIGN)   # no engine line to vet a safe square with
    assert "Nxd8" in board_facts_block(ST2_8) and "replies to the check" in board_facts_block(ST2_8)
    assert "gxf6 (+1)" in board_facts_block(ST2_4)


def test_board_facts_block_is_as_before_with_the_switch_off(facts_off):
    from src.prompt_builder import board_facts_block

    st2 = board_facts_block(ST2_2)
    assert "one more attacker" not in st2 and "material on the board" not in st2
    assert "fork is available now: Qxd5+" in board_facts_block(MATE2_NO)


def test_engine_block_adds_safety_and_balance(facts_on):
    from src.prompt_builder import engine_note_block

    turn_facts.collect(chess.Board(G1_RESIGN), G1_LINES, kinds=turn_facts.ENGINE_KINDS)   # as engine_note does
    block = engine_note_block("[Engine] … Best: Nd5.", fen=G1_RESIGN)
    assert "Counted on the board by exchange" in block
    assert re.search(r"d5.{0,60}safe squares", block.split("Counted on the board")[1])
    assert "Counted on the board" not in engine_note_block("[Engine] … Best: Nf3.", fen=chess.STARTING_FEN)
    st2 = engine_note_block("[Engine] …", fen=ST2_2)   # no engine facts collected: the board's own (balance)
    assert "one more attacker" in st2


def test_engine_note_collects_the_vetted_facts(facts_on, monkeypatch):
    from src import voice_engine_note as ven

    fake = {"lines": [{"pv": "f6d5 c2c4", "score": -0.55, "depth": 12}, {"pv": "f6g8 d2d4", "score": -1.05, "depth": 12}]}
    monkeypatch.setattr(ven, "analyze_timed", lambda *a, **k: fake)
    monkeypatch.setattr(ven, "analyze_cached", lambda *a, **k: fake)
    monkeypatch.setattr(ven, "_threat_analysis", lambda fen: {"lines": []})
    note = ven.engine_note(G1_RESIGN, movetime_ms=100)
    assert note and "Counted on the board" not in note["note"]          # the voice/lesson line is as before
    got = turn_facts.recent(G1_RESIGN, engine=True)
    assert got and got[0].kind == "piece_safety" and got[0].data["safe"] == ["d5", "g8"]


def test_lesson_engine_block_is_unchanged(facts_on):
    from src.prompt_builder import lesson_engine_block

    assert "Counted on the board" not in lesson_engine_block("[Engine] x")


# ── opening ideas ──────────────────────────────────────────────────────────────────────────────────────────────

def _book_rows():
    import csv

    from src import openings_book

    rows = []
    for d in openings_book._CANDIDATE_DIRS:
        if d and openings_book._readable_dir(d):
            for p in sorted(Path(d).glob("*.tsv")):
                with open(p, encoding="utf-8") as fh:
                    rows += list(csv.DictReader(fh, delimiter="\t"))
            break
    return rows


_SAN = r"(?:O-O(?:-O)?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?)[+#]?(?![\w-])"
_SEQ = re.compile(rf"(\d+)\.(\.\.)?\s*({_SAN}(?:\s+(?:\d+\.(?:\.\.)?\s*)?{_SAN})*)")


def _sequences(idea: str):
    """(move number, black to move, [san…]) for every numbered run of moves in *idea*."""
    for m in _SEQ.finditer(idea):
        sans = [re.sub(r"^\d+\.(\.\.)?", "", t) for t in m.group(3).split()]
        sans = [t for t in sans if t]
        if sans:
            yield int(m.group(1)), bool(m.group(2)), sans


def test_every_idea_names_a_book_line_and_its_moves_are_legal():
    from src.prompt_builder import opening_ideas

    rows = _book_rows()
    if not rows:
        pytest.skip("no ECO book TSVs here (OPENINGS_TSV_DIR)")
    ideas = opening_ideas()
    assert len(ideas) >= 40
    for name, idea in ideas.items():
        family = [r for r in rows if r["name"] == name or r["name"].startswith(name + ":") or r["name"].startswith(name + ",")]
        assert family, f"{name}: not a name of the ECO book"
        starts = []
        for r in family:
            b = chess.Board()
            for tok in r["pgn"].split():
                if not tok[0].isdigit():
                    b.push_san(tok)
            starts.append(b)
        for number, black, sans in _sequences(idea):
            ok = False
            for start in list(starts):
                # the sequence starts at this book position, or a few plies before it along the same line
                for back in range(0, 12):
                    b = start.copy()
                    for _ in range(min(back, len(b.move_stack))):
                        b.pop()
                    if b.fullmove_number != number or (b.turn == chess.BLACK) != black:
                        continue
                    try:
                        for san in sans:
                            b.push_san(san)
                    except ValueError:
                        continue
                    ok = True
                    starts.append(b)
                    break
                if ok:
                    break
            assert ok, f"{name}: {number}{'...' if black else '.'}{' '.join(sans)} is not legal from its book line"


def test_idea_lines_carry_the_29_10_truths(facts_on):
    from src.prompt_builder import opening_idea_line

    assert re.search(r"Slav.{0,80}c6", opening_idea_line(SLAV) or "")
    assert "Queen's Gambit Declined" in opening_idea_line(SLAV)
    assert re.search(r"\bsharp", opening_idea_line(NAJDORF) or "")
    assert re.search(r"Alekhine.{0,120}(2\.e5 Nd5|Nd5)|invites? .{0,10}e5", opening_idea_line(G1_RESIGN) or "")
    assert opening_idea_line(chess.STARTING_FEN) is None


def test_the_longest_name_wins():
    from src.prompt_builder import idea_for_name

    assert idea_for_name("Sicilian Defense: Najdorf Variation, English Attack, Anti-English")[0] == \
        "Sicilian Defense: Najdorf Variation, English Attack"
    assert idea_for_name("Sicilian Defense: Najdorf Variation")[0] == "Sicilian Defense: Najdorf Variation"
    assert idea_for_name("Sicilian Defense: Bowdler Attack")[0] == "Sicilian Defense"
    assert idea_for_name("Sicilian Defenses") is None


def test_no_idea_line_with_the_switch_off(facts_off):
    from src.prompt_builder import opening_idea_line

    assert opening_idea_line(SLAV) is None


# ── the resign block ───────────────────────────────────────────────────────────────────────────────────────────

def test_resign_block_gives_the_final_evaluation(facts_on, monkeypatch):
    from src import game_mode
    from src.tools.game_play import resign_evaluation

    monkeypatch.setattr(game_mode, "_evaluate", lambda fen, pov: (-60, "Nd5"))   # the student (Black) at −0.6
    text = resign_evaluation({"fen": G1_RESIGN, "student_color": "black"})
    assert "+0.6 (from White's side)" in text and "not lost" in text and "Do not justify the resignation" in text
    assert "Nd5" not in text
    monkeypatch.setattr(game_mode, "_evaluate", lambda fen, pov: (-9995, None))
    assert "forced mate for White" in resign_evaluation({"fen": G1_RESIGN, "student_color": "black"})
    monkeypatch.setattr(game_mode, "_evaluate", lambda fen, pov: (-500, None))
    assert "clearly worse" in resign_evaluation({"fen": G1_RESIGN, "student_color": "black"})


def test_resign_block_without_an_engine_keeps_the_rule(facts_on, monkeypatch):
    from src import game_mode
    from src.tools.game_play import resign_evaluation

    def boom(*a, **k):
        raise RuntimeError("no engine")

    monkeypatch.setattr(game_mode, "_evaluate", boom)
    text = resign_evaluation({"fen": G1_RESIGN, "student_color": "black"})
    assert text.startswith("Do not justify the resignation")


def test_resign_block_as_before_with_the_switch_off(facts_off):
    from src.tools.game_play import resign_evaluation

    assert resign_evaluation({"fen": G1_RESIGN, "student_color": "black"}) == ""


# ── the P8 fact controls ───────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("control", [c for c in CONTROLS if c["fact_kind"] != "fork"], ids=lambda c: c["id"])
def test_fact_controls(control, facts_on):
    board = chess.Board(control["fen"])
    lines = G1_LINES if control["fen"] == G1_RESIGN else None
    facts = turn_facts.facts_for_board(board, lines, (control["fact_kind"],))
    assert facts and all(f.proven for f in facts)
    blob = json.dumps([f.data for f in facts]) + " ".join(f.text for f in facts)
    assert control["keep"] in blob, control["why"]
