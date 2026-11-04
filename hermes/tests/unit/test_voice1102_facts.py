"""Voice 02.11 (production, a game, White's move 9): facts the model cannot merge wrongly.

On r2qk1nr/ppp3pp/3p4/2b1p3/1nP5/3b1NP1/PP1P1PBP/R1BQK2R w KQkq - 0 9 the voice coach proposed «пойти ферзём на d1»
with the queen on d1, twice «пешкой с d2 на d3» with Black's bishop on d3, and said O-O was impossible «потому что
поле f2 под боем слона c5». The note listed «f1 is attacked by the bishop d3» for castling and, apart, «the pawn f2 is
attacked by the bishop c5»; the model merged the two.

The coach's rule facts (voice note, text turn) now say (src/board_rules.rule_facts, explicit):
  * castling with the king's squares that decide it, every attacked one with its attackers, and the attacked squares
    next to them (the rook's, the pawns' in front) named as not mattering;
  * the side to move's pawn moves and queen moves as a closed list, and the pawns that cannot move with why.
The lesson tutor, the hidden board and the knowledge topics keep the facts as they were (explicit off).
"""

import random
import re

import chess
import pytest

from src import config
from src.board_rules import castling_facts, castling_status, move_facts, rule_facts

LIVE = "r2qk1nr/ppp3pp/3p4/2b1p3/1nP5/3b1NP1/PP1P1PBP/R1BQK2R w KQkq - 0 9"

# (fen, wing, expected: "legal" | squares that bar it | a reason prefix, door: attacked neighbours said not to matter)
CASTLING = [
    (LIVE, "O-O", {"f1": ["the black bishop on d3"]}, ["e2", "f2"]),
    # the Italian: Bc5 hits f2 — castling is legal, the pawn f2 does not matter
    ("r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4", "O-O", "legal", ["f2"]),
    # the same for Black: Bc4 hits f7, O-O is legal
    ("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R b KQkq - 5 4", "O-O", "legal", ["f7"]),
    # g1 attacked by the bishop c5: the king may not land there (the rook h1 hangs to the rook h8: its square is left
    # out of the castling clause, review-facts 03.11)
    ("r3k2r/8/8/2b5/8/8/8/R3K2R w KQkq - 0 1", "O-O", {"g1": ["the black bishop on c5"]}, ["f2", "h2"]),
    # f1 and g1 both attacked, by two pieces
    ("4k3/8/b7/8/8/7n/8/4K2R w K - 0 1", "O-O",
     {"f1": ["the black bishop on a6"], "g1": ["the black knight on h3"]}, ["e2", "f2"]),
    # long castling: d1 attacked by the rook d8
    ("3rk3/8/8/8/8/8/8/R3K3 w Q - 0 1", "O-O-O", {"d1": ["the black rook on d8"]}, ["d2"]),
    # long castling legal with b1 attacked: only the rook passes it
    ("1r2k3/8/8/8/8/8/8/R3K2R w KQ - 0 1", "O-O-O", "legal", ["b1", "b2"]),
    # Black: f8 attacked by the bishop a3
    ("r3k2r/8/8/8/8/B7/8/4K3 b kq - 0 1", "O-O", {"f8": ["the white bishop on a3"]}, ["e7"]),
    # in check
    ("4k3/8/8/8/8/8/8/r3K2R w K - 0 1", "O-O", "the king is in check", []),
    # the right lost with king and rook at home
    ("r3k2r/8/8/8/8/8/8/R3K2R w Kkq - 0 1", "O-O-O", "the right to castle is lost", []),
    # plain legal, nothing attacked nearby
    ("r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1", "O-O", "legal", []),
    ("r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R b KQkq - 0 1", "O-O-O", "legal", []),
]

LABEL = {"O-O": "short castling (O-O)", "O-O-O": "long castling (O-O-O)"}


def _wing_text(fen: str, wing: str) -> str:
    fact = castling_facts(chess.Board(fen), explicit=True)
    assert fact, fen
    parts = re.split(r"; (?=(?:short|long) castling)", fact[0].split(": ", 1)[1])
    found = [p for p in parts if p.startswith(LABEL[wing])]
    assert len(found) == 1, (fen, parts)
    return found[0]


@pytest.mark.parametrize("fen,wing,expected,door", CASTLING)
def test_castling_names_the_deciding_squares_and_closes_the_door(fen, wing, expected, door):
    board = chess.Board(fen)
    assert board.is_valid()
    text = _wing_text(fen, wing)
    legal = castling_status(board)[wing][0]
    if expected == "legal":
        assert legal and text.startswith(f"{LABEL[wing]} is legal now"), text
    elif isinstance(expected, str):
        assert not legal and expected in text, text
    else:
        assert not legal and "is NOT possible now — the king would" in text, text
        for sq, attackers in expected.items():
            assert f"{sq}, which {' and '.join(attackers)} attacks" in text, text
        # no square off the king's way is named as the reason
        named = set(re.findall(r"(?:pass|land on) ([a-h][1-8]), which", text))
        assert named == set(expected), text
    if door:
        # squares only, scoped to castling (review-facts 03.11: «an attack on the rook a1 does not matter» read as safety)
        tail = text.split("an attack on ", 1)[1].split(" does not stop it")[0]
        assert tail.split(", ") == door, text
        rank = "1" if board.turn == chess.WHITE else "8"
        kings = ("e", "f", "g") if wing == "O-O" else ("e", "d", "c")
        assert f"castling depends only on {', '.join(k + rank for k in kings)}" in text
    else:
        assert "does not stop it" not in text, text


def test_the_live_board_says_f1_and_puts_f2_aside():
    text = _wing_text(LIVE, "O-O")
    assert text.startswith("short castling (O-O) is NOT possible now — the king would pass f1, which the black "
                           "bishop on d3 attacks; castling depends only on e1, f1, g1; an attack on e2, f2 does "
                           "not stop it")
    assert "c5" not in text.split("chasing")[0]  # the bishop c5 is not a reason


def test_door_squares_are_really_attacked_and_never_the_kings_own():
    for fen, wing, _exp, door in CASTLING:
        board = chess.Board(fen)
        for item in door:
            sq = chess.parse_square(item.split()[-1])
            assert board.is_attacked_by(not board.turn, sq), (fen, item)
            assert chess.square_name(sq) not in ("e1", "f1", "g1", "d1", "c1", "e8", "f8", "g8", "d8", "c8")


def test_castling_fact_even_when_only_own_pieces_bar_it():
    # review-facts 03.11: with no castling line at all «могу ли я рокироваться?» had no fact to answer from
    start = castling_facts(chess.Board(), explicit=True)
    assert len(start) == 1 and start[0].count("pieces stand between the king and the rook") == 2
    assert start[0].count("nothing else stops it") == 2
    assert castling_facts(chess.Board("4k3/8/8/8/8/8/8/5K1R w - - 0 1"), explicit=True) == [
        "White: no castling any more — the king has left e1"]
    assert castling_facts(chess.Board()) == [] and castling_facts(chess.Board("4k3/8/8/8/8/8/8/5K1R w - - 0 1")) == []


# ── the moves of the side to move ───────────────────────────────────────────


def _random_boards(n: int, seed: int = 1102) -> list[chess.Board]:
    rng = random.Random(seed)
    out = []
    while len(out) < n:
        b = chess.Board()
        for _ in range(rng.randint(4, 60)):
            moves = list(b.legal_moves)
            if not moves:
                break
            b.push(rng.choice(moves))
        if not b.is_game_over():
            out.append(chess.Board(b.fen()))
    return out


BOARDS = [chess.Board(LIVE), chess.Board()] + [chess.Board(f) for f, *_ in CASTLING] + _random_boards(30)


def _parse(fact: str) -> dict:
    out = {"queens": {}, "pawns": None, "stuck": {}}
    fact = fact.replace(" (or =R, =B, =N)", "")  # a promotion said once for every piece (review-facts 03.11)
    for part in fact.split(" to move — ", 1)[1].split("; "):
        m = re.match(r"the queen ([a-h][1-8]) can play only (.+)$", part)
        none = re.match(r"the queen ([a-h][1-8]) has no legal move now$", part)
        if none:
            out["queens"][none.group(1)] = []
        elif m:
            out["queens"][m.group(1)] = m.group(2).split(", ")
        elif part.startswith("the only pawn moves: "):
            rest = part[len("the only pawn moves: "):]
            out["pawns"] = [] if rest == "none" else rest.split(", ")
        elif part.startswith("pawns that cannot move: "):
            for sq, why in re.findall(r"([a-h][1-8]) \(([^)]*)\)", part):
                out["stuck"][sq] = why
        else:
            raise AssertionError(part)
    return out


@pytest.mark.parametrize("idx", range(len(BOARDS)))
def test_the_pawn_and_queen_moves_are_exactly_the_legal_ones(idx):
    board = BOARDS[idx]
    facts = move_facts(board)
    color = board.turn
    pawns = board.pieces(chess.PAWN, color)
    queens = board.pieces(chess.QUEEN, color)
    if not pawns and not queens:
        assert facts == []
        return
    got = _parse(facts[0])
    assert facts[0].startswith(("White" if color else "Black") + " to move — ")
    legal = [m for m in board.legal_moves if m.promotion in (None, chess.QUEEN)]
    assert set(got["queens"]) == {chess.square_name(q) for q in queens}
    for q in queens:
        want = {board.san(m) for m in legal if m.from_square == q}
        assert set(got["queens"][chess.square_name(q)]) == want
    if pawns:
        assert set(got["pawns"]) == {board.san(m) for m in legal if m.from_square in pawns}
    for sq, why in got["stuck"].items():
        s = chess.parse_square(sq)
        assert s in pawns and not any(m.from_square == s for m in board.legal_moves)
        if why != "pinned":
            ahead = chess.parse_square(why.split()[0])
            occ = board.piece_at(ahead)
            assert occ is not None and why.endswith(chess.piece_name(occ.piece_type))


def test_the_live_board_has_no_d2_d3_and_no_queen_to_d1():
    fact = move_facts(chess.Board(LIVE))[0]
    got = _parse(fact)
    assert got["queens"] == {"d1": ["Qa4+", "Qb3", "Qc2", "Qe2"]}
    assert got["pawns"] == ["a3", "a4", "b3", "g4", "h3", "h4"]
    assert got["stuck"]["d2"] == "d3 is taken by the black bishop"
    assert "d3" not in got["pawns"] and "Qd1" not in fact


def test_a_pinned_pawn_and_a_promotion():
    pinned = chess.Board("4k3/8/8/b7/8/8/3P4/4K3 w - - 0 1")  # Ba5 pins d2 to Ke1
    assert _parse(move_facts(pinned)[0])["stuck"] == {"d2": "pinned"}
    promo = chess.Board("4k3/1P6/8/8/8/8/8/4K3 w - - 0 1")
    assert _parse(move_facts(promo)[0])["pawns"] == ["b8=Q+"]  # under-promotions left out


def test_in_check_no_stuck_list():
    board = chess.Board("4k3/8/8/8/8/8/3PP3/r3K3 w - - 0 1")  # Ra1+, Kf2 only; the pawns cannot block
    fact = move_facts(board)[0]
    assert "cannot move" not in fact and "the only pawn moves: none" in fact


# ── who gets them: the coach yes, the lesson tutor no ───────────────────────


def test_default_rule_facts_are_as_before():
    board = chess.Board(LIVE)
    plain = rule_facts(board, with_tablebase=False)
    assert plain[0].startswith("White: short castling (O-O) is NOT possible now — f1 is attacked by the black "
                               "bishop on d3 — the king may not pass through an attacked square")
    assert not any(" to move — " in f or "decide O-O" in f for f in plain)
    assert castling_facts(chess.Board("1r2k3/8/8/8/8/8/8/R3K2R w KQ - 0 1"))[0].endswith(
        "(b1 is attacked, but only the rook passes it — that does not matter)")


def test_explicit_rule_facts_and_the_switch(monkeypatch):
    board = chess.Board(LIVE)
    rich = rule_facts(board, with_tablebase=False, explicit=True)
    assert any("castling depends only on e1, f1, g1" in f for f in rich) and any(f.startswith("White to move — the queen d1") for f in rich)
    monkeypatch.setattr(config, "COACH_EXPLICIT_RULES", False)
    assert rule_facts(board, with_tablebase=False, explicit=True) == rule_facts(board, with_tablebase=False)


def test_game_over_has_no_move_facts():
    mate = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")
    assert move_facts(mate) == []
    assert rule_facts(mate, with_tablebase=False, explicit=True) == rule_facts(mate, with_tablebase=False)


def test_text_board_block_carries_them_only_when_asked(monkeypatch):
    from src.prompt_builder import board_facts_block

    rich = board_facts_block(LIVE, explicit_rules=True)
    assert "the king would pass f1" in rich and "the only pawn moves: a3, a4, b3, g4, h3, h4" in rich
    plain = board_facts_block(LIVE)  # the lesson tutor's fallback
    assert "the only pawn moves" not in plain and "f1 is attacked by the black bishop on d3" in plain


def test_engine_note_rules_for_the_coach_only():
    from src.voice_engine_note import _rules

    board = chess.Board(LIVE)
    assert any("an attack on e2, f2 does not stop it" in f for f in _rules(board, True))
    assert not any("does not matter" in f for f in _rules(board))


def test_voice_game_note_gets_the_rules(monkeypatch):
    from src import server

    text = server._voice_game_rules(LIVE)
    assert text.startswith(" Rules of the position (verified on the board): White: short castling (O-O) is NOT "
                           "possible now — the king would pass f1")
    assert "the queen d1 can play only Qa4, Qb3, Qc2, Qe2" in text  # no «+»/«#» in the game note (review-facts 03.11)
    assert "pawn structure" not in text and "Pieces on the board — White: Ke1, Qd1" in text
    assert "tablebase" not in text
    monkeypatch.setattr(config, "COACH_EXPLICIT_RULES", False)
    assert server._voice_game_rules(LIVE) == ""
    assert server._voice_game_rules("not a fen") == ""


def test_voice_board_note_asks_the_engine_note_for_them(monkeypatch):
    from src import server

    seen = {}

    def fake(fen, **kw):
        seen.update(kw)
        return {"fen": fen, "note": "[Engine] Best: c4", "mate_in": None}

    monkeypatch.setattr(server, "engine_note", fake)
    note = server._voice_board_note(LIVE, None, "u-1102")
    assert note["note"].endswith("[Engine] Best: c4") and seen == {"explicit_rules": True}


def test_the_voice_game_note_in_a_live_game(monkeypatch):
    from src import game_mode, hypothetical, server
    from tests.unit.test_audio_audit_2026_10_27 import USER, _Engine, _game_with

    eng = _Engine()
    monkeypatch.setattr(game_mode, "_engine_move", eng.move)
    monkeypatch.setattr(game_mode, "_evaluate", eng.evaluate)
    monkeypatch.setattr(hypothetical, "live_game_note",
                        lambda fen, *a, **k: {"eval": 0.3, "threat": None, "note": "- Evaluation: +0.3 for White."})
    from src.sessions import session_store

    session = _game_with(["e4", "Nf3"])
    try:
        fen = session.get_board(session.active_board_id).fen
        note = server._voice_board_note(fen, session.id, USER)
    finally:
        session_store._sessions.pop(session.id, None)
    assert note["kind"] == "game"
    assert "Rules of the position (verified on the board): White: " in note["note"]
    assert "White to move — the queen d1 can play only" in note["note"]
    assert "never name the best move" in note["note"]
