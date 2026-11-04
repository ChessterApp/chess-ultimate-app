"""Fix 01.11, package F3 (board rules): prevents, checks_geometry and retreat_cover read by their parts, judged on the
right board, and a prevention judged by a forcing line, not only by the static exchange (review-fp, review-miss of
57bb4868). Positive cases are wordings outside the graded row; negative ones are true sentences and the readings that
must stay unjudged.
"""
from __future__ import annotations

import sys
from pathlib import Path

import chess
import pytest

from src import claim_rules as R
from src import config
from src.claim_types import Claim, MoveRef, Ref

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
from ctx_fixture import run_answer  # noqa: E402

CASTLE = "r2qk2r/ppp2ppp/2np1n2/4p3/2b1P3/2N2N2/PPP2PPP/R1BQK2R w KQkq - 0 8"  # castle-ru: Bc4 covers f1
CARO = "rnbqkbnr/pp1ppppp/2p5/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"  # 1.e4 c6
LUCENA = "1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1"
LEGAL = "rn1qkbnr/ppp2p1p/3p2p1/4N3/2B1P3/2N5/PPPP1PPP/R1BbK2R w KQkq - 0 7"  # Legal's mate: 7.Bxf7+ Ke7 8.Nd5#


@pytest.fixture(autouse=True)
def _relations_on(monkeypatch):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW", raising=False)


def _ctx(fen: str, moves: str = "", question: str = ""):
    from src.answer_check import CheckContext

    b = chess.Board(fen)
    for m in moves.split():
        b.push_san(m)
    ctx = CheckContext.from_fens([b.fen()], [moves] if moves else [], question=question)
    ctx.language = "ru"
    return ctx


def _issues(sentences, fen, moves=""):
    if isinstance(sentences, str):
        sentences = [sentences]
    return run_answer(list(sentences), _ctx(fen, moves))[-1][1]


def _rel(sentence, rel):
    return [c for c in R.extract(sentence, {}) if c.rel == rel]


# ── prevents: the reading ──────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "Играй d4 — тогда чёрные не смогут сыграть d5.",
    "d4 мешает чёрным поставить пешку на d5.",
    "Ход d4 не пускает пешку на d5.",
    "После d4 у чёрных пропадает ход d5.",
    "d4 лишает чёрных хода ...d5.",
    "Займи центр ходом d4, чтобы чёрные не играли d5.",
    "d4 запрещает ...d5.",
    "Сыграв d4, ты не дашь чёрным пойти d5.",
    "d4 предотвращает d5.",
    "После d4 чёрным будет уже нельзя ответить d5.",
    "d3 не позволит чёрным сыграть d5.",
    "d4 перекрывает дорогу пешке d7 на d5.",
    "После d4 пешка d7 уже не дойдёт до d5.",
    "Ход d4 делает d5 невозможным.",
    "Лучший ход — Nc3: он не даёт чёрным сыграть d5.",
    "Сыграй d4, и ход d5 у чёрных отпадёт.",
    # held-out style: other verbs, cases and orders
    "Nf3 помешает чёрным продвинуть пешку на d5.",
    "Ход d4 не позволяет сопернику спокойно сыграть ...d5.",
    "После 2.d4 чёрные уже не сумеют сыграть d5.",
])
def test_prevents_wordings_are_read_and_cut(sentence):
    claims = _rel(sentence, "prevents")
    assert claims and claims[0].to.sq == "d5"
    issues = _issues(sentence, CARO)
    assert any("can still play d5" in i for i in issues), issues


@pytest.mark.parametrize("sentence", [
    # an object square, a piece standing, no move
    "Лучший план — d4, атакуя c5 и не давая чёрным спокойно сыграть d5.",
    "Конь на f6 стоит хорошо, не давая белым сыграть e5.",
    "Играй d4: конь c3 не даёт чёрным сыграть d5.",
    # a denied stop, a question, a later time, «всё равно», advice not to play
    "d4 не мешает чёрным сыграть d5.",
    "d4 не даёт чёрным сыграть d5?",
    "Играй d4, чтобы потом не дать чёрным сыграть d5.",
    "После d4 чёрные всё равно не смогут сыграть d5 без подготовки.",
    "После d4 не играй сразу d5.",
    "После d4 чёрные не играют d5 сразу, а готовят его.",
    # a pawn standing as the stopper
    "Пешкой d4 белые блокируют продвижение d5.",
    # a hypothetical with another condition, a hedge, an outpost (kept, not played)
    "Если чёрные сыграют e6, d4 не даст им сыграть d5.",
    "d4 может помешать чёрным сыграть d5.",
    "d4 мешает чёрным закрепиться на d5.",
])
def test_prevents_not_read(sentence):
    assert not _rel(sentence, "prevents") or not _issues(sentence, CARO)


def test_prevents_target_after_a_capture_verb_is_the_victim_square():
    c = _rel("Лучше всего d3, не давая коню f6 спокойно забрать пешку e4.", "prevents")[0]
    assert c.to.sq == "e4" and c.to.piece == "N" and c.kind.startswith("from:f6")  # (|calm: «спокойно», final 02.11)
    # after 4.d3 Nxe4 dxe4 loses the knight: true, not cut
    assert not _issues("Лучше всего d3, не давая коню f6 спокойно забрать пешку e4.", chess.STARTING_FEN,
                       "e4 e5 Nf3 Nc6 Bc4 Nf6")


# ── prevents: the judge ────────────────────────────────────────────────────────────────────────────────────────
def test_prevents_holds_when_a_forcing_line_punishes_the_move():
    """review-fp R4: 3...Nf6?? walks into Qxf7# — the static exchange on f6 alone called it safe."""
    for s in ("Ход Qh5, не давая чёрным спокойно выдвинуть коня на f6: на это Qxf7#.",
              "Qh5 — нападая на f7 и не позволяя чёрным спокойно сыграть Nf6."):
        assert not _issues(s, chess.STARTING_FEN, "e4 e5 Bc4 Nc6")


def test_forcing_gain_finds_mate_fork_and_nothing():
    mate = chess.Board("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4")
    assert R.forcing_gain(mate) >= R._MATE_SCORE // 2
    fork = chess.Board("r3k3/8/8/8/8/8/8/4K1N1 w - - 0 1")  # Nf3? no; knight fork on c7 is not reachable: nothing
    assert R.forcing_gain(fork) == 0
    hanging = chess.Board("4k3/8/8/3q4/8/8/8/3RK3 w - - 0 1")
    assert R.forcing_gain(hanging) == 9


def test_prevents_move_must_be_the_side_to_move():
    """A move of the other side is not judged after a pass (review-miss: the board after 1.e4 alone excused it)."""
    claim = Claim(rel="prevents", subj=Ref(side=chess.WHITE), objs=(Ref(sq="e4", piece="P"),), source="rules",
                  move=MoveRef(san="d5", piece="P", to="d5"), to=Ref(sq="e4", piece="P"))
    assert R.judge_prevents(claim, chess.Board(CARO), None).status == "undecided"


def test_prevents_ignores_intermediate_plies_of_an_earlier_line():
    """review-miss: «Nc3, не давая чёрным сыграть d5» after «Каро-Канн — 1. e4 c6.» was excused by the board after 1.e4."""
    issues = _issues(["Защита Каро-Канн — 1. e4 c6. ", "Лучший ход — Nc3, не давая чёрным сыграть d5."], CARO)
    assert any("can still play d5" in i for i in issues)


def test_prevents_castling_target():
    # 1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.d3 Nf6: White's Bg5 does not stop Black castling
    assert any("O-O" in i for i in _issues("Bg5, не давая чёрным рокироваться.", chess.STARTING_FEN,
                                             "e4 e5 Nf3 Nc6 Bc4 Bc5 d3 Nf6"))
    # a check stops it this move
    assert not _issues("Bb5+, не давая чёрным рокироваться.", chess.STARTING_FEN, "e4 e5 Nf3 d6 d4 Nf6 Nc3 Be7")


def test_prevention_frame_and_start():
    assert R.prevention_frame("2.d4 — занимая центр и не давая чёрным спокойно ")
    assert R.prevention_frame("2.d4, not letting Black ")
    assert R.prevention_frame("Займи центр ходом d4, чтобы чёрные не ")
    assert not R.prevention_frame("Лучший ход — ")
    assert not R.prevention_frame("Не мешает и ")
    s = "стоит, не давая чёрным поставить коня на f6"
    assert R.prevention_start(s) == s.index("не давая")
    assert R.prevention_start("сыграй Nf3 и развивайся") is None
    assert R.prevention_start("d4 не мешает чёрным") is None


# ── checks_geometry ────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "Затем Kc7, и когда чёрная ладья начнёт шаховать по вертикали d, ладья d4 перекроет линию.",
    "После Kc7 ладья a2 будет давать шахи по линии d, а мост на d4 их закроет.",
    "Ладья на d4 нужна, чтобы прикрыть короля на c7 от шахов по вертикали d.",
    "Белый король выходит на c7, а чёрная ладья шахует его по линии d — тут и пригодится мост.",
    "Король уходит на c7, и на любой шах по вертикали d белые закрываются ладьёй.",
    "После Kc7 ладья чёрных идёт на d2 и шахует по вертикали d.",
    "Когда король на c7, шах по d-вертикали отражается ладьёй d4.",
    "Затем Kc7, и ладья на d4 закроет короля от шахов по линии d.",
    # held-out style
    "Как только белый король встанет на c7, чёрная ладья даст шах по d-вертикали.",
    "После Kc7 последуют шахи чёрной ладьи по вертикали «d».",
])
def test_checks_geometry_wordings_are_cut(sentence):
    issues = _issues(sentence, LUCENA)
    assert any("off the d-file" in i for i in issues), issues


@pytest.mark.parametrize("sentence", [
    # the king on the line, the king leaving, denied checks, escaping checks, the checker's own king
    "После Kc7 ладья чёрных шахует по вертикали c, король отходит на b6.",
    "Затем белый король выходит из-под пешки (Kc7), и когда чёрная ладья начнёт шаховать по вертикали c, король "
    "пойдёт к ладье, а ладья d4 закроет шах на вертикали b.",
    "Затем белый король выходит (Kc7), и чёрная ладья начнёт шаховать по вертикали d, как только король вернётся на d6.",
    "После Kc7 шахов по вертикали d уже не будет.",
    "После Kc7 король уходит от шахов по вертикали d.",
    "Затем чёрный король отходит (Kc7), и когда чёрная ладья начнёт шаховать по вертикали d, белые закроются.",
    "Мост на d4 спасает от шахов по вертикали d.",
    "Чёрные станут шаховать по вертикали d, но ладья d4 встанет между.",
    # «с d-вертикали» may say where the checking piece stands
    "Когда король на c7, шах с d-вертикали отражается ладьёй d4.",
])
def test_checks_geometry_not_cut(sentence):
    assert not any("off the" in i for i in _issues(sentence, LUCENA))


def test_checks_geometry_static_king_and_a_diagonal_checker_not_judged():
    """Corpus (puzzle heavy-piece-checkmates): «ферзь ставит шах по линии f» with the king on e4 — the queen stands on
    the f-file (Qf3+); a piece that checks along a diagonal too is judged only after a king move told."""
    fen = "8/8/8/8/4k3/3N4/2N3K1/3Q4 w - - 0 1"
    s = "Король на e4 зажат: ферзь ставит шах по линии f, а оба коня (c2 и d3) держат поля d4, e5 и e4-отходы — убежать некуда."
    assert not any("off the f-file" in i for i in _issues(s, fen))


def test_checks_geometry_king_side_from_the_board():
    claim = Claim(rel="checks_along", subj=Ref(piece="R", side=chess.BLACK), objs=(), kind="file:d", source="rules",
                  move=MoveRef(san="Kc7", piece="K", to="c7"), to=Ref(sq="c7", piece="K"))
    assert R.judge_checks_geometry(claim, chess.Board(LUCENA), None).status == "false"
    # the checker's king is the nearer one: whose king walked is not known
    near_black = chess.Board("8/2k5/8/8/8/8/r7/K7 w - - 0 1")
    claim2 = Claim(rel="checks_along", subj=Ref(piece="R", side=chess.BLACK), objs=(), kind="file:d", source="rules",
                   move=MoveRef(san="Kc6", piece="K", to="c6"), to=Ref(sq="c6", piece="K"))
    assert R.judge_checks_geometry(claim2, near_black, None).status == "undecided"


# ── retreat_cover ──────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "Сыграй b3: слон c4 будет вынужден отступить и перестанет держать f1.",
    "После b3 слону придётся уйти с диагонали a6–f1, и рокировка станет возможна.",
    "b3 прогоняет слона, и поле f1 освобождается.",
    "Ход b3 выгоняет слона с c4, после чего f1 больше не под ударом.",
    "Атакуй слона пешкой: b3, и он уже не сможет контролировать f1.",
    "b3 — слон уходит, а с ним уходит и контроль над f1.",
    "После b3 чёрный слон отступает, и ты спокойно рокируешься.",
    "Подними пешку на b3 — слон отойдёт, и f1 перестанет простреливаться.",
    "Сыграв b3, ты заставишь слона покинуть диагональ f1–a6.",
    "Если сыграть b3, слон уйдёт, и поле f1 больше не будет атаковано.",
    "b3, и слон c4 вынужден отступить на e6 — f1 свободно.",
    "После b3 у слона есть только одно отступление — e6, откуда f1 не прикрыт.",
    "Ходом b3 белые отгоняют слона от f1.",
    "8.b3 — и чёрный слон теряет контроль над f1.",
    # held-out style
    "Пешка на b3 погонит слона, и короткая рокировка сразу станет доступна.",
])
def test_retreat_cover_wordings_are_cut(sentence):
    issues = _issues(sentence, CASTLE)
    assert any("Ba6" in i and "f1" in i for i in issues), issues


def test_retreat_cover_read_where_another_check_cuts_first():
    """«слон c4 уже не будет бить поле f1» after b3: the relation check cuts it first (the bishop on c4 attacks f1
    after 8.b3); the board rule reads it too and judges it false."""
    s = "После b3 слон c4 уже не будет бить поле f1."
    claims = _rel(s, "retreat_cover")
    assert claims and claims[0].subj.sq == "c4"
    assert R.judge_retreat_cover(claims[0], chess.Board(CASTLE), None).status == "false"
    assert _issues(s, CASTLE)


@pytest.mark.parametrize("sentence", [
    "После b3 слон может отступить на a6 и всё равно держать f1.",
    "Даже после b3 слон сохранит контроль над f1 с поля a6.",
    "Если слон c4 уйдёт на e6, рокировка станет доступна.",
    # a line told with its retreat named: after 8...Be6 f1 is free
    "После b3 слон отступит на e6, и поле f1 освободится.",
    # a condition after the consequence, a hedge
    "b3 прогоняет слона, и f1 освобождается, но только если слон уйдёт на e6.",
    "После b3 слон может уйти, и поле f1 освободится.",
])
def test_retreat_cover_not_cut(sentence):
    assert not any("still covers f1" in i or "need not move" in i for i in _issues(sentence, CASTLE))


def test_retreat_cover_free_needs_an_empty_square():
    claim = Claim(rel="retreat_cover", subj=Ref(piece="B"), objs=(Ref(sq="f1"),), source="rules",
                  kind="chase:b3|free|forced")
    occupied = chess.Board("r2qk2r/ppp2ppp/2np1n2/4p3/2b1P3/2N2N2/PPP2PPP/R1BQKB1R w KQkq - 0 8")
    assert R.judge_retreat_cover(claim, occupied, None).status == "undecided"
    assert R.judge_retreat_cover(claim, chess.Board(CASTLE), None).status == "false"


def test_retreat_cover_true_when_every_retreat_gives_the_square_up():
    """r2qk2r/1pp2ppp/p1np1n2/…: after b3 only e6 is safe (a6 is taken by Black's own pawn, b5/d3/e2 are lost)."""
    fen = "r2qk2r/1pp2ppp/p1np1n2/4p3/P1b1P3/2N2N2/1PP2PPP/R1BQK2R w KQkq - 0 8"
    assert not _issues("После b3 слон вынужден отступить на e6, и поле f1 он уже не прикрывает.", fen)
    assert not _issues("b3 прогоняет слона, и рокировка станет возможна.", fen)


# ── mate in one (review-fp: «у них мат в один ход» in Legal's mate) ────────────────────────────────────────────
def test_mate_in_one_is_read_from_the_board():
    from src.answer_check_rules import _mate_in_issues

    b = chess.Board(LEGAL)
    b.push_san("Bxf7+")
    b.push_san("Ke7")
    ctx = _ctx(b.fen())
    ctx.engine_eval, ctx.engine_mate = 20.0, None
    assert _mate_in_issues("белые позади на 7 пешек по материалу, но у них мат в один ход.", ctx) == []
    assert _mate_in_issues("здесь нет мата в один ход.", ctx) == ["there IS a forced mate in 1 here (engine)"]
    quiet = _ctx(chess.STARTING_FEN)
    quiet.engine_eval, quiet.engine_mate = 0.3, None
    assert _mate_in_issues("здесь мат в один ход.", quiet) == ["there is no forced mate in 1 here (engine)"]
    winning = _ctx("4k3/8/8/8/8/8/8/Q3K3 w - - 0 1")
    winning.engine_eval, winning.engine_mate = 20.0, None
    assert _mate_in_issues("здесь мат в два хода.", winning) == []
