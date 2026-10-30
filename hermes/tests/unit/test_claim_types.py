"""The claim schema of the relation checker (src/claim_types.py, plan 30.10 WP-0)."""
import dataclasses
import json
from pathlib import Path

import chess
import pytest

from src.claim_types import (ALL_RELATIONS, Claim, MoveRef, Pos, Ref, Verdict, find_moves, find_squares,
                             parse_san_token)

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "relations"


def _recorded():
    data = json.loads((FIX / "recorded_claims.json").read_text())
    claims = [c for cl in data["eval"].values() for c in cl]
    claims += [c for x in data["triage_extra"] for c in x["claims"]]
    return claims


def test_every_recorded_claim_round_trips():
    claims = _recorded()
    assert len(claims) == 278  # 270 eval extractions + 8 of the 11 triage extras (3 have no claim)
    for d in claims:
        c = Claim.from_dict(d)
        assert c.to_dict() == d
        assert Claim.from_dict(c.to_dict()) == c
        assert json.loads(json.dumps(c.to_dict())) == d  # JSON-compatible
        assert c.rel in ALL_RELATIONS


def test_reads_the_llm_schema():
    """The model extractor's JSON (design-llm): obj + objs, sides as letters, moves as SAN, n, plies, question."""
    raw = {"span": None, "rel": "attacks", "subj": {"piece": "N", "sq": "g5", "side": "w"}, "obj": {"sq": "f7"},
           "objs": [{"sq": "h7"}], "pos": {"at": "after", "moves": ["Bb5+", "Bd7", "Qe2"]}, "n": 2, "question": True}
    c = Claim.from_dict(raw, source="llm")
    assert c.rel == "attack" and c.source == "llm" and c.count == 2 and c.question == "which"
    assert c.subj == Ref(sq="g5", piece="N", side=chess.WHITE)
    assert [o.sq for o in c.objs] == ["f7", "h7"]
    assert [m.san for m in c.pos.moves] == ["Bb5+", "Bd7", "Qe2"]
    assert c.pos.moves[0] == MoveRef(san="Bb5+", piece="B", to="b5")
    back = Claim.from_dict({"rel": "attacks", "subj": None, "pos": {"at": "back", "plies": 1}})
    assert back.pos == Pos(at="back", plies_back=1, tense="past")
    assert Claim.from_dict({"rel": "attacks", "subj": None, "pos": {"at": "shb2"}}).pos == Pos(at="shown", plies_back=2)
    assert Claim.from_dict({"rel": "attacks", "subj": None, "pos": {"at": "gen"}}).pos.at == "skip"
    me = Claim.from_dict({"rel": "defends", "subj": {"side": "me", "piece": "Q"}, "obj": {"sq": "d8"}})
    assert me.subj.owner == "you" and me.subj.side is None


def test_nested_positions_and_verdicts_round_trip():
    c = Claim(rel="defend", subj=Ref(piece="N", sq="c3"), objs=(Ref(sq="c2", piece="P"),), question="which",
              pos=Pos(at="after", alts=(Pos(at="after", moves=(MoveRef(san="Nc3", piece="N", to="c3"),)),
                                        Pos(at="after", moves=(MoveRef(san="Nd2", piece="N", to="d2"),)))),
              span=(3, 40), move=MoveRef(san="Qc1", piece="Q", to="c1"), kind="block")
    assert Claim.from_dict(json.loads(json.dumps(c.to_dict()))) == c
    v = Verdict("false", "after 4.e5", "White's pawn on e5 attacks d6 and f6 — not Black's knight on g8")
    assert Verdict.from_dict(v.to_dict()) == v


def test_types_are_frozen_and_hashable():
    c = Claim(rel="attack", subj=Ref(sq="f6", piece="N"), objs=(Ref(sq="d4"),))
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.rel = "defend"  # type: ignore[misc]
    assert hash(c) == hash(Claim.from_dict(c.to_dict()))
    assert {c: 1}[Claim.from_dict(c.to_dict())] == 1  # a state value may be a claim: immutable all the way down


@pytest.mark.parametrize("text, expected", [
    ("Конь сыграл Кf6.", [MoveRef(san="Nf6", piece="N", to="f6")]),
    ("Чёрные только что сыграли 135...Qg1, напав на коня g7",
     [MoveRef(san="Qg1", piece="Q", to="g1", number="135...", side=chess.BLACK), MoveRef(san="g7", piece="P", to="g7")]),
    ("Рокировка O-O решает обе задачи", [MoveRef(san="O-O", piece="K", castle="short")]),
    ("потом 0-0-0", [MoveRef(san="O-O-O", piece="K", castle="long")]),
    ("Ход е4 занимает центр", [MoveRef(san="e4", piece="P", to="e4")]),  # Cyrillic е
    ("1.e4 e5 2.Nf3", [MoveRef(san="e4", piece="P", to="e4", number="1.", side=chess.WHITE),
                       MoveRef(san="e5", piece="P", to="e5"),
                       MoveRef(san="Nf3", piece="N", to="f3", number="2.", side=chess.WHITE)]),
    ("Лучше ...Сg4 со связкой", [MoveRef(san="Bg4", piece="B", to="g4", side=chess.BLACK)]),
    ("Qxd5+ выигрывает", [MoveRef(san="Qxd5+", piece="Q", to="d5", capture=True)]),
])
def test_find_moves(text, expected):
    assert find_moves(text) == expected


def test_parse_san_token_keeps_a_full_from_square():
    assert parse_san_token("Qh4xe1").frm == "h4"
    assert parse_san_token("Nbd7").frm is None
    assert parse_san_token("4.e5") == MoveRef(san="e5", piece="P", to="e5", number="4.", side=chess.WHITE)


def test_find_squares():
    assert find_squares("Пешка е4 и конь на f6") == [("e4", 6), ("f6", 19)]
    assert find_squares("a10, h9 and 135") == []
