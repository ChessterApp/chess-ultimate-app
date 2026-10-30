"""Moves and «piece on square» told after a written line, judged where the line got to (prod check 29.10).

r-zugzwang: «Чёрный король обязан отойти в сторону: Kd6 — и белый король заходит через d5» (Kd5 next to the black
king on d6); castle-00: «лучший ход — b3: ты отгоняешь слона, а если он отступит на a6, то с боку грозит bxc4»
(c4 empty after ...Ba6); square-no: «после Ke5 белые играют a6, и ты обязан идти Kd6 … Теперь замри: пешка на a7,
ты на d6» (the pawn is on a6). src/answer_check_scene.py walks the line strictly, moves in words included.
"""

import chess
import pytest

from src.answer_check import CheckContext, check_sentence

pytestmark = pytest.mark.unit


def _run(ctx, sentences):
    """Each sentence checked in order on one context, as the gate does; the scene's issues of each."""
    return [[i for i in check_sentence(s, ctx) if "(the line written" in i] for s in sentences]


def _scene(issues):
    return [i for i in issues if "(the line written" in i]


# ── r-zugzwang: get_topic put the study position on the board over the start position ─────────────────────────

ZUG = "8/8/4k3/8/4K3/4P3/8/8 b - - 0 1"


def _zug_ctx():
    ctx = CheckContext.from_fens([chess.STARTING_FEN], question="Что такое цугцванг? Покажи пример на доске.")
    ctx.add(ZUG)  # the set_fen of the tool (src/server.py adds each action's fen)
    return ctx


def test_zugzwang_king_entering_next_to_the_other_king():
    out = _run(_zug_ctx(), [
        "Вот на доске чистейший пример: чёрные на ходу, белые держат оппозицию — короли стоят друг напротив друга.",
        "Чёрный король обязан отойти в сторону: Kd6 — и белый король заходит через d5.",
    ])
    assert out[0] == []
    assert len(out[1]) == 1
    issue = out[1][0]
    assert "after 1...Kd6" in issue and "the white king cannot go to d5" in issue
    assert "next to the black king on d6" in issue and "Kf5" in issue


@pytest.mark.parametrize("sentence, expect", [
    ("После 1...Kd6 2.Kd5 белые заходят в тыл.", "Kd5 is impossible"),
    ("After 1...Kd6 the white king goes to d5.", "the white king cannot go to d5"),
    ("Кd6 — и белый король идёт на d5.", "the white king cannot go to d5"),  # Russian К written for the king
    ("Смотри. 1... Kd6 2. Kd5 — и белые прорываются.", "Kd5 is impossible"),  # numbers with spaces, two sentences
    ("Чёрные отступают: Kd6, и тогда белый король встанет на d5.", "the white king cannot go to d5"),
])
def test_zugzwang_paraphrases(sentence, expect):
    issues = _scene(check_sentence(sentence, _zug_ctx()))
    assert any(expect in i for i in issues), issues


@pytest.mark.parametrize("sentence", [
    "Чёрный король обязан отойти в сторону: Kd6 — и белый король заходит через f5.",  # legal: the outflanking
    "После 1...Kf6 2.Kd5 белый король прорывается вперёд.",  # after Kf6, d5 is free
    "Kd6 — и белый король уже не может зайти на d5.",  # the truth, denied
    "Kd6 — а если бы белый король пошёл на d5?",  # a question
    "Kd6 — и король идёт на d5.",  # whose king: the black one may go there
    "Kd6 — или белый король идёт на d5, если чёрные сыграют Kf6.",  # another branch
    "После 1...Kd6 2.Kd5? белые сразу ошибаются.",  # a move the coach marks as a mistake: not his line
])
def test_zugzwang_unjudged(sentence):
    assert _scene(check_sentence(sentence, _zug_ctx())) == []


def test_zugzwang_next_sentence_without_a_continuation_is_not_the_line():
    ctx = _zug_ctx()
    assert _run(ctx, ["Чёрные играют Kd6.", "Белый король идёт на d5."]) == [[], []]


def test_zugzwang_next_sentence_going_on_with_the_line():
    ctx = _zug_ctx()
    out = _run(ctx, ["Чёрные играют Kd6.", "Тогда белый король заходит через d5."])
    assert out[0] == [] and any("cannot go to d5" in i for i in out[1]), out


# ── castle-00: the bishop that left c4 cannot be taken there ───────────────────────────────────────────────────

CASTLE = "r2qk2r/ppp2ppp/2np1n2/4p3/2b1P3/2N2N2/PPP2PPP/R1BQK2R w KQkq - 0 8"
CASTLE_ANSWER = [
    "Нет, 0-0 сейчас нельзя — слон с c4 бьёт f1, и король не может пройти через атакованную клетку.",
    "И прогнать слона недостаточно: он может уйти на a6, b5, d3 или e2 и всё равно держать f1 под ударом.",
    "Сейчас слон c4 атакует ещё и твой пункт a2, поэтому лучший ход — b3: ты отгоняешь слона, а если он отступит "
    "на a6, то с боку грозит bxc4.",
    "А вот длинная рокировка станет возможна, когда ты уберёшь фигуры с c1 и d1 — тогда король уйдёт на c1 под защиту.",
    "Пока же просто развивайся: Qe2, Be3, и король спокойно укроется позже, когда f1 перестанет быть под боем.",
]


def test_castle_capture_on_the_square_the_bishop_left():
    out = _run(CheckContext.from_fens([CASTLE], question="А если 0-0?"), CASTLE_ANSWER)
    assert [len(x) for x in out] == [0, 0, 1, 0, 0], out
    issue = out[2][0]
    assert "after 8. b3 Ba6" in issue and "bxc4 is impossible" in issue
    assert "c4 is empty" in issue and "from c4 to a6" in issue


@pytest.mark.parametrize("sentence", [
    "Играй b3, и если слон уйдёт на a6, белые сыграют bxc4.",
    "Сыграй b3: слон отходит на a6, и тогда bxc4.",
])
def test_castle_paraphrases(sentence):
    issues = _scene(check_sentence(sentence, CheckContext.from_fens([CASTLE])))
    assert any("bxc4 is impossible" in i for i in issues), issues


@pytest.mark.parametrize("sentence", [
    "Сыграй b3: если слон останется на c4, то грозит bxc4.",  # the bishop stays: bxc4 is there
    "Сыграй b3, а если слон уйдёт на a6 — тогда и рокировка не нужна.",
    "Сыграй b3 или сразу bxc4.",  # another branch
    "Play b3: if the bishop retreats to a6, b3-b4 gains space.",
])
def test_castle_unjudged(sentence):
    assert _scene(check_sentence(sentence, CheckContext.from_fens([CASTLE]))) == []


# ── square-no: the position named is not the one the line reaches ─────────────────────────────────────────────

SQUARE = "8/8/8/P4k2/8/8/8/7K b - - 0 1"
SQUARE_ANSWER = [
    "Нет, король не успевает — но не из-за гонки, а из-за того, что поле d6 под контролем.",
    "Играй Ke4, это самая упорная защита.",
    "Смотри: после Ke5 белые играют a6, и ты обязан идти Kd6 — иначе пешка просто идёт в ферзи.",
    "Теперь замри: пешка на a7, ты на d6.",
]


def test_square_pawn_named_where_the_line_does_not_put_it():
    out = _run(CheckContext.from_fens([SQUARE], question="Я чёрными, мой ход. Король успеет к пешке?"), SQUARE_ANSWER)
    assert [len(x) for x in out] == [0, 0, 0, 1], out
    issue = out[3][0]
    assert "after 1...Ke5 2. a6 Kd6" in issue and "no pawn on a7" in issue and "stands on a6" in issue


def test_square_voice_utterance_in_one_check():
    """The voice check gets the whole utterance at once (src/server.py voice/check): the sentences inside it."""
    text = " ".join(SQUARE_ANSWER[2:])
    issues = _scene(check_sentence(text, CheckContext.from_fens([SQUARE])))
    assert any("no pawn on a7" in i for i in issues), issues


@pytest.mark.parametrize("sentence", [
    "После 1...Ke5 2.a6 Kd6 пешка на a7, ты на d6.",
    "After 1...Ke5 2.a6 Kd6 the pawn is on a7.",
])
def test_square_paraphrases(sentence):
    issues = _scene(check_sentence(sentence, CheckContext.from_fens([SQUARE])))
    assert any("no pawn on a7" in i for i in issues), issues


@pytest.mark.parametrize("sentences", [
    ["После 1...Ke5 2.a6 Kd6 3.a7 пешка на a7, ты на d6."],  # the line reaches it
    ["Смотри: после Ke5 белые играют a6, и ты идёшь Kd6.", "Теперь представь: пешка на a7, ты на d6."],  # imagined
    ["Смотри: после Ke5 белые играют a6, и ты идёшь Kd6.", "Сейчас пешка на a5, а ты на f5."],  # the board as it is
    ["Смотри: после Ke5 белые играют a6, и ты идёшь Kd6.", "Теперь замри: пешка на a6, ты на d6."],  # right
    ["Смотри: после Ke5 белые играют a6, и ты идёшь Kd6.", "Пешка на a7 — это уже ферзь через ход."],  # not «now»
    ["Смотри: после Ke5 белые играют a6, и ты идёшь Kd6.", "Теперь пешка на a7?"],  # a question
])
def test_square_unjudged(sentences):
    out = _run(CheckContext.from_fens([SQUARE]), sentences)
    assert all(x == [] for x in out), out


# ── the same walk found real errors in the lesson corpus (prod runs 19–23.10) ─────────────────────────────────

def test_mate_skipping_the_moves_that_open_the_line():
    """«Тогда Rh7#» after 1.Nxf6+ Kh8: the g7 pawn still stands between the f7 rook and h7 (Rh6+ gxh6 first)."""
    ctx = CheckContext.from_fens(["2r2b2/5Rpk/5pR1/5P2/6N1/8/3r3P/6K1 w - - 0 1"], question="Какой здесь первый ход?")
    out = _run(ctx, [
        "Первый ход — **Nxf6+**, конь забирает пешку f6 с шахом.",
        "Смысл в том, что у чёрных единственный ответ — Kh8, а конь на f6 уже не даёт королю дышать по g8.",
        "Тогда **Rh7#** — вторая ладья заходит на h7 и матует.",
    ])
    assert out[:2] == [[], []]
    assert any("Rh7# is impossible" in i and "pawn on g7 stands between the rook on f7 and h7" in i for i in out[2]), out


def test_recapture_with_a_pinned_pawn():
    ctx = CheckContext.from_fens(["r2k2nr/p1p3qp/2pp3b/3Qn3/5p2/2B5/PPP3PP/RN1R3K w - - 0 1"])
    issues = _scene(check_sentence("Смотри: 1.Фxe5 dxe5 2.Сxg7 — и ферзь чёрных гибнет.", ctx))
    assert any("dxe5 is impossible" in i and "pinned to the black king by the rook on d1" in i for i in issues), issues


def test_king_stepping_next_to_a_pawn_that_guards_the_square():
    ctx = CheckContext.from_fens(["8/8/6p1/5p2/5P1K/5k1P/8/8 b - - 0 1"])
    issues = _scene(check_sentence("Если сразу 1...Kxf4, то 2.Kh5 и белый король успевает съесть g6 и f5 — ничья.", ctx))
    assert any("Kh5 is impossible" in i and "attacked by the black pawn on g6" in i for i in issues), issues


# ── lines the walk must not judge ─────────────────────────────────────────────────────────────────────────────

def test_a_whole_mating_line_over_several_sentences_passes():
    ctx = CheckContext.from_fens(["4B2r/8/8/3K2p1/5kPp/R6P/5rP1/4N3 w - - 0 1"])
    out = _run(ctx, [
        "Первый ход — **g3+**.",
        "Это шах, и у чёрных единственный ответ: **hxg3** — пешка вынуждена взять.",
        "Дальше идёт — **Rf3+**, и после **Rxf3** матует — **Ng2#**: чёрный король на f4 зажат.",
    ])
    assert out == [[], [], []]


def test_a_line_after_moves_not_followed_is_not_judged():
    """«Дальше идёт …» after moves the walk could not read: the line's position is unknown."""
    ctx = CheckContext.from_fens(["4B2r/8/8/3K2p1/5kPp/R6P/5rP1/4N3 w - - 0 1"])
    assert _run(ctx, ["Дальше идёт — **Rf3+**, и после **Rxf3** матует — **Ng2#**."]) == [[]]


@pytest.mark.parametrize("sentence", [
    "После Rf1 ладья перейдёт на f2.",  # the side that has just moved: a plan
    "После Kd5 белый король идёт на f5, но ты успеваешь забрать пешку — ничья.",  # a route, not one move
    "Сначала Rd8+ выгоняет короля, потом твой король идёт на f2–e3–e4.",  # a route
    "Re8! — после Qxe8 следует Nxf6+, и король обязан уйти на h8, а затем Nxe8 забирает ферзя.",  # a move not read
    "Тогда **Rh7#** — ладья заходит на h7 и матует.",  # no line before: where it is played is not known
])
def test_plans_routes_and_unread_moves(sentence):
    ctx = CheckContext.from_fens(["2r2rk1/2p3p1/pp1p1p2/2nR4/P3P2q/2Q2P1P/1PP2PK1/4R3 w - - 0 1"])
    assert _scene(check_sentence(sentence, ctx)) == []


def test_a_line_of_a_diagram_only_named_in_a_tool_is_not_walked():
    """A lesson's position the tool only named in its text (not on the screen): its line is not judged here."""
    ctx = CheckContext.from_fens(["8/8/8/P4k2/8/8/8/7K b - - 0 1"])
    ctx.add_text('{"fen": "2r2b2/5Rpk/5pR1/5P2/6N1/8/3r3P/6K1 w - - 0 1"}')
    assert _run(ctx, ["Первый ход — **Nxf6+**, и после Kh8 следует Rh7#."]) == [[]]


def test_a_game_position_on_the_way_is_not_a_start_without_a_number():
    """«Bxc6» fits only the position after 3...a6, passed long ago: without a move number the line is not walked from
    there (the coach may be naming the game's move, not starting a line)."""
    board = chess.Board()
    moves = ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Bxc6", "dxc6"]
    for san in moves:
        board.push_san(san)
    ctx = CheckContext.from_fens([board.fen()])
    ctx.add_line(" ".join(moves))
    assert _run(ctx, ["Bxc6 — и чёрный король идёт на f7."]) == [[]]
