"""Integration 02.11 (next-1031 + K1–K8): the patches the packages wrote for code they did not own, on new boards.

- K4 → K5's grammar: a piece «с X» is the mover of a told move only if it could reach the move's square
  (castle-rights #2, live 02.11: «чёрный конь с f6» was taken to have made 5.Nc3 → "the piece on c3 is White's").
- K6 → the answer check's issue texts: an undefended claim whose piece is not on the board now leaves no
  «defended (by )», and «no any queen» is not written. (K6's recapture hunk is covered by K5's own restatement rule.)
"""
from __future__ import annotations

import chess
import pytest

from src import answer_check as ac
from src.rewrite_proof import malformed


def _board(moves: str) -> chess.Board:
    b = chess.Board()
    for m in moves.split():
        b.push_san(m)
    return b


def _check(sentence, board, student=chess.WHITE):
    return ac.check_sentence(sentence, ac.CheckContext.from_fens([board.fen()], student_color=student))


# 1.e4 e5 2.d3 Nf6: Black's knight on f6 attacks e4, White's knight b1 can go to d2
OPEN_D3 = _board("e4 e5 d3 Nf6")
# 1.e4 e5 2.Nf3: White's knight on f3
KNIGHT_F3 = _board("e4 e5 Nf3")


@pytest.mark.unit
class TestPieceFromSquareIsTheMover:
    def test_another_piece_from_its_square_is_not_the_mover(self):
        s = "Подумай о Nd2 — заодно защитишь пешку e4, которую чёрный конь с f6 уже атакует."
        assert _check(s, OPEN_D3) == []

    def test_the_relation_of_that_piece_is_still_judged(self):
        s = "Подумай о Nd2 — заодно защитишь пешку e4, которую чёрный конь с f6 уже не атакует."
        assert any("f6" in i and "e4" in i for i in _check(s, OPEN_D3))

    def test_a_piece_that_can_reach_the_square_is_still_the_mover(self):
        # the knight from g1 did make Nf3; f3 does not attack d5
        s = "Сыграй Nf3: белый конь с g1 сразу нападает на пешку d5."
        assert _check(s, _board("e4 d5")) != []

    def test_could_go_geometry(self):
        from src.claim_grammar import _could_go
        sq = chess.parse_square
        assert not _could_go(chess.KNIGHT, sq("f6"), sq("c3"))
        assert _could_go(chess.KNIGHT, sq("b1"), sq("c3"))
        assert _could_go(chess.BISHOP, sq("f1"), sq("b5")) and not _could_go(chess.BISHOP, sq("f1"), sq("f5"))
        assert _could_go(chess.KING, sq("e1"), sq("g1")) and not _could_go(chess.KING, sq("e1"), sq("e3"))
        assert not _could_go(chess.ROOK, sq("a1"), sq("a1"))


@pytest.mark.unit
class TestIssueTexts:
    def test_a_pawn_capture_restated_after_words_is_not_a_recapture(self):
        # «cxd5, то есть ...: cxd5» names one move twice (1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.cxd5 is the exchange line)
        b = _board("d4 d5 c4 e6 Nc3 Nf6")
        issues = _check("Самое простое — cxd5, то есть сразу разменять центр: cxd5.", b)
        assert not any("after cxd5" in i for i in issues)
        assert all(not malformed(i) for i in issues)

    def test_a_real_pawn_recapture_pair_is_still_judged(self):
        # «Nxd5 exd5» with no e-pawn able to take back for Black (1.e4 d5 2.exd5 Nf6 3.Nc3): judged as before
        b = _board("e4 d5 exd5 Nf6 Nc3")
        assert any("exd5" in i for i in _check("После Nxd5 exd5 у чёрных всё в порядке.", b))

    def test_an_undefended_claim_about_another_piece_now_leaves_no_empty_defender_list(self):
        # 1.e4 e5 2.Nf3 d6 3.d4 Bg4 4.dxe5 Bxf3: «Конь f3 ничем не защищён» — the knight was defended; on f3 now
        # stands Black's bishop with no defender. Not «the bishop on f3 is defended (by )»; the wrong piece is told
        b = _board("e4 e5 Nf3 d6 d4 Bg4 dxe5")
        before = b.fen()
        b.push_san("Bxf3")
        ctx = ac.CheckContext.from_fens([b.fen(), before], student_color=chess.WHITE)
        issues = ac.check_sentence("Конь f3 ничем не защищён.", ctx)
        assert issues and all("(by )" not in i and not malformed(i) for i in issues)
        assert any("not a knight" in i for i in issues)

    def test_no_any_is_not_written(self):
        b = _board("e4 e5 Nf3 Nc6")
        for i in _check("Можно сразу Qxh7.", b) + _check("Хорош ход Qxf7#.", b):
            assert "no any" not in i


# ── one module-level name, one meaning ──────────────────────────────────────────────────────────────────────────
# Packages merged side by side can each define the same helper name; the later definition then silently replaces the
# earlier one for every caller (K3's _NOMINATIVE_PIECE, an English-aware pattern, replaced the Russian one that
# _square_subject_issues used, and «d4 attacks the knight on e5» was cut). A name may be rebound only by a wrapper
# that takes the old value («f = wrap(f)»).
def _rebound_names(path):
    import ast
    tree = ast.parse(path.read_text())
    first, out = {}, []
    for node in tree.body:
        names, value = [], None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        for name in names:
            if name in first:
                wraps = value is not None and any(isinstance(n, ast.Name) and n.id == name for n in ast.walk(value))
                if not wraps:
                    out.append((name, first[name], node.lineno))
            else:
                first[name] = node.lineno
    return out


@pytest.mark.unit
def test_no_module_level_name_is_defined_twice():
    from pathlib import Path
    src = Path(__file__).resolve().parents[2] / "src"
    found = {p.name: r for p in sorted(src.glob("*.py")) if (r := _rebound_names(p))}
    assert found == {}


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "d4 attacks the knight on e5.",
    "e4 attacks the knight on d5.",
])
def test_an_english_object_after_the_verb_is_not_the_subject(sentence):
    # a white pawn attacking a black knight, told square-first in English: true, not judged false
    boards = {"d4": "r1bqkb1r/pppp1ppp/5n2/4n3/3PP3/8/PPP2PPP/RNBQKBNR w KQkq - 0 5",
              "e4": "rnbqkb1r/pppppppp/8/3n4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 3"}
    fen = boards[sentence[:2]]
    ctx = ac.CheckContext.from_fens([fen], student_color=chess.WHITE)
    assert ac.check_sentence(sentence, ctx) == []


@pytest.mark.unit
def test_the_russian_subject_after_the_verb_is_still_read():
    # «Поле c3 атакует конь e4»: the knight stands after the verb and is the subject; it does attack c3 — true;
    # «Поле h6 атакует конь e4» is false (the knight does not reach h6)
    fen = "rnbqkb1r/pppp1ppp/8/4p3/4n3/2N5/PPPP1PPP/R1BQKBNR w KQkq - 0 4"
    ctx = ac.CheckContext.from_fens([fen], student_color=chess.WHITE)
    assert ac.check_sentence("Поле c3 атакует конь e4.", ctx) == []
    ctx = ac.CheckContext.from_fens([fen], student_color=chess.WHITE)
    assert ac.check_sentence("Поле h6 атакует конь e4.", ctx) != []


# ── a square glued to a line noun names the line ────────────────────────────────────────────────────────────────
# With K4's patch a piece «с X» that could not have made the told move is read as a piece standing on X; «слон с
# f4-диагонали бьёт по королю» (the corpus's Immortal Game, 23.Be7#) then became "no bishop on f4". «f4-диагонали»,
# «h5-e8-диагонали», «h-вертикали» name a line, not the piece's square.
# 1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.Ng5 h6: 5.Bxf7+ is the told move; the bishop comes from c4
FRIED = _board("e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 h6")


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Сильнее всего 5.Bxf7+: слон с d3-диагонали бьёт по королю на e8.",
    "Сильнее всего 5.Bxf7+: слон с h5-e8-диагонали бьёт по королю на e8.",
    "Сильнее всего 5.Bxf7+: слон с d3 – диагонали бьёт по королю на e8.",
])
def test_a_square_naming_a_line_is_not_where_the_piece_stands(sentence):
    assert _check(sentence, FRIED) == []


@pytest.mark.unit
def test_a_piece_from_a_square_is_still_read_without_a_line_noun():
    # the bishop did not come from d3 and no bishop stands there after the move: still judged
    assert any("d3" in i for i in _check("Сильнее всего 5.Bxf7+: слон с d3 бьёт по королю на e8.", FRIED))
    # the knight from g5 stands on g5 and does not attack h8: still judged
    assert any("h8" in i for i in _check("Сильнее всего 5.Bxf7+: конь с g5 бьёт по ладье h8.", FRIED))


@pytest.mark.unit
def test_tokens_of_a_line_square():
    from src.claim_grammar import tokenize
    toks = tokenize("слон с f4-диагонали бьёт по королю на d8")
    piece = next(t for t in toks if t.kind == "PIECE" and t.text.startswith("слон"))
    assert piece.sq is None
    assert any(t.kind == "SQ" and t.route and chess.square_name(t.sq) == "f4" for t in toks)
