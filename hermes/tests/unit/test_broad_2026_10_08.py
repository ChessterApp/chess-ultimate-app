"""Broad fixes of 2026-10-08, after the client's «Что если я пойду Се3?».

One test per class of failure seen on production (06–08.10), not per case:
moves written any way, a move already played, fragments of cut sentences,
thinking aloud, arrows standing for moves, short English sentences, a lone FEN
read as English, en passant and defences misjudged, invented game history.
"""

import chess
import pytest

from src.answer_check import CheckContext, SentenceGate, check_sentence, language_issue
from src.board_markup import MarkupFilter
from src.move_matcher import named_moves
from src.prompt_builder import _script_language, question_moves

ALEX = "r1bqk2r/2pn1pp1/2pp4/p1b2P1p/4P3/2NB4/PPP3PP/R1BQ1R1K w kq - 0 1"

# The battery behind the matcher: 48 everyday ways to write four moves of the client's position.
BATTERY = {
    "Be3": ["Се3", "Сe3", "Be3", "С:е3", "Сс1-е3", "Сc1-e3", "с1-е3", "c1e3", "Bc1e3", "С е3", "C e3", "Ce3", "се3",
            "СЕ3", "bishop e3", "слон е3", "слоном на е3", "слон на е3", "слона на e3", "пойду слоном е3",
            "а если слон пойдёт на е3", "поставлю слона на е3", "Слон c1 на e3"],
    "Qxh5": ["Фh5", "Ф:h5", "Фxh5", "ферзём на h5", "ферзь бьёт h5", "возьму пешку h5 ферзём", "Qh5", "взять на h5",
             "съем пешку h5"],
    "Nb5": ["Кb5", "Кв5", "Кб5", "конь b5", "конём на b5", "Nb5", "конь прыгает на b5"],
    "f6": ["f6", "f5-f6", "пешка f6", "пешкой на f6", "а если f6?", "двину пешку f на f6", "ф6"],
}


def _ask(words: str) -> str:
    starts = ("а если", "пойду", "поставлю", "возьму", "съем", "двину", "взять")
    return words + "?" if words.startswith(starts) else f"Что если я пойду {words}?"


@pytest.mark.parametrize("san,words", [(s, w) for s, ws in BATTERY.items() for w in ws])
def test_every_way_of_writing_a_move(san, words):
    assert san in [m["san"] for m in question_moves(_ask(words), ALEX) if m.get("legal")]


@pytest.mark.parametrize("text", [
    "Почему конь f6 висит?", "После 1.e4 e5 что играть?", "Мат в 3 хода здесь есть?", "с 3 фигурами",
    "Пешка e4 под ударом?", "Что делать со слоном d3?", "Слон d3 смотрит на h7.", "Поле e5 слабое?",
])
def test_a_square_or_a_piece_is_not_a_move(text):
    assert named_moves(text, chess.Board(ALEX)) == []


def test_a_move_already_played_is_not_illegal():
    named = question_moves("Я сыграл Qb6. Это мат?", "k7/8/1Q6/8/8/8/8/2K5 b - - 0 1")
    assert named[0]["verdict"].startswith("already played")


def test_a_cut_sentence_leaves_no_fragment():
    gate = SentenceGate(CheckContext.from_fens([ALEX]))
    assert gate.feed("Сначала нужно было поставить чёрную ") == []  # nothing of it goes out before its check


def test_a_self_correction_after_an_ellipsis_is_dropped():
    gate = SentenceGate(CheckContext.from_fens([ALEX]))
    out = gate.feed("Второй вариант — сразу Be3, блокируя... нет, точнее защищая f1. ")
    assert any(o[1] for o in out)


def test_an_arrow_standing_for_the_move_is_written():
    f = MarkupFilter("r2qkb1r/pp2nppp/3p4/2pNN1B1/1BbnP3/3P4/PPP2PPP/R2bK2R w KQkq - 1 1")
    out, _ = f.feed("Ставит мат: [[arrows: b4f8]]. После [[arrows: d5f6]] чёрным остаётся взятие. "
                    "Смотри на доску [[arrows: e5f7]] — тут всё ясно.")
    out += f.flush()
    assert "мат: b4–f8." in out and "После Nf6+ чёрным" in out and "доску — тут" in out


@pytest.mark.parametrize("text,english", [
    ("I'll pull up the game.", True), ("I'll look at the position carefully.", True),
    ("(Fried Liver Attack)", False), ("**DrNykterstein** (Lichess):", False), ("1.e4 e5 2.Nf3 Nc6 3.Bb5", False),
])
def test_a_short_english_sentence_in_a_russian_answer(text, english):
    assert bool(language_issue(text, "ru")) is english


@pytest.mark.parametrize("message,lang", [
    (ALEX, None), ("https://lichess.org/abc12345", None), ("What should I play here?", "en"), ("Что тут? " + ALEX, "ru"),
])
def test_a_fen_or_a_link_carries_no_language(message, lang):
    assert _script_language(message) == lang


def test_en_passant_is_a_capture_of_the_pawn_that_passed():
    ep = "rnbqkbnr/1pp1pppp/p7/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3"
    assert check_sentence("Пешка e5 бьёт пешку d5, которая только что прыгнула через два поля, и встаёт на d6.",
                          CheckContext.from_fens([ep])) == []
    assert check_sentence("Пешка e5 бьёт пешку d5.", CheckContext.from_fens(["rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq - 0 3"]))


def test_a_defence_is_of_ones_own_piece():
    fen = "r1bq1b1r/ppp3pp/2n1k3/3np3/2B5/5Q2/PPPP1PPP/RNB1K2R w KQ - 2 8"
    assert check_sentence("Потому что ферзь d8 и король e6 держат коня, размен вам ничего не даёт.", CheckContext.from_fens([fen])) == []


def test_the_student_who_played_the_move_owns_it():
    ctx = CheckContext.from_fens(["k7/8/1Q6/8/8/8/8/2K5 b - - 0 1"], student_color=chess.WHITE)
    assert check_sentence("У чёрных король на a8, а твой ферзь на b6 отнимает у него все поля.", ctx) == []


def test_invented_game_history():
    fen = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w kq - 6 5"
    s = "Партия шла так: 1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.Nc3? — и вот здесь чёрные успели походить конём на f6."
    assert check_sentence(s, CheckContext.from_fens([fen]))
    assert check_sentence(s, CheckContext.from_fens([fen], ["1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5"])) == []


@pytest.mark.parametrize("sentence,caught", [
    ("Конь с ф3 прыгает на д5.", True),  # transliterated squares in a speech transcript
    ("Самое полезное сейчас — убрать коня с d3, где он стоит неуклюже.", True),  # the bishop stands there
    ("Можно перевести коня с c3 на e2.", False),
])
def test_squares_and_pieces_in_other_spellings(sentence, caught):
    fen = ALEX if "d3" in sentence or "c3" in sentence else "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
    assert bool(check_sentence(sentence, CheckContext.from_fens([fen]))) is caught


# A lesson puzzle with castling rights its kings and rooks no longer allow (16 of the site's 187).
BAD_CASTLING = "r1q1kb1r/pppn1npp/8/4p1B1/8/1Q6/PPP2PPP/RN2R1K1 w Qkq - 0 1"


def test_a_lesson_fen_with_impossible_castling_is_repaired_not_refused():
    from src.fen_repair import repair_fen

    assert repair_fen(BAD_CASTLING) == "r1q1kb1r/pppn1npp/8/4p1B1/8/1Q6/PPP2PPP/RN2R1K1 w kq - 0 1"
    assert repair_fen(chess.STARTING_FEN) == chess.STARTING_FEN  # a valid FEN is left exactly as it is
    assert repair_fen("garbage") == "garbage" and repair_fen(None) is None
    assert repair_fen("4k3/8/8/8/8/8/8/4K3 w - e3 0 1") == "4k3/8/8/8/8/8/8/4K3 w - - 0 1"


def test_the_engine_tools_and_notes_take_such_a_fen():
    import json

    from src.prompt_builder import board_facts_block
    from src.tools import discover_and_register
    from tools.registry import registry

    discover_and_register()
    out = json.loads(registry.dispatch("check_moves", {"fen": BAD_CASTLING, "moves": ["Qe6+"]}))
    assert "error" not in out and out["results"][0]["legal"] is True
    assert board_facts_block(BAD_CASTLING)
    assert [m["san"] for m in question_moves("А если Qe6+?", BAD_CASTLING)] == ["Qe6+"]


@pytest.mark.parametrize("text,flagged", [
    ("第一着是 **Kd4**——把马跳向中心，切断白方后的前路。", True),
    ("مرحبا بك في الشطرنج", True),
    ("Защита Грюнфельда (Grünfeld) и система Рети (Réti) — гипермодерн.", False),
])
def test_a_sentence_in_another_script(text, flagged):
    assert bool(language_issue(text, "ru")) is flagged


@pytest.mark.parametrize("text,fixed", [
    ("Первый ход — **Kxf2** (конь берёт пешку f2 с шахом).", "Первый ход — **Nxf2** (конь берёт пешку f2 с шахом)."),
    ("Итальянская партия — 1.e4 e5 2.Kf3 Kc6 3.Cc4.", "Итальянская партия — 1.e4 e5 2.Nf3 Nc6 3.Bc4."),
    ("Движок даёт линию 1.Kc3 Kb8 2.Qg7 Ka8.", "Движок даёт линию 1.Kc3 Kb8 2.Qg7 Ka8."),  # an endgame line: the king
    ("Король обязан ответить, а после Kxf2 конь f6 прыгает на g4.", "Король обязан ответить, а после Kxf2 конь f6 прыгает на g4."),
])
def test_russian_piece_letters_typed_in_latin(text, fixed):
    from src.answer_check import normalize_notation

    assert normalize_notation(text) == fixed


START4 = "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"


@pytest.mark.parametrize("sentence,caught", [
    ("На b3 пешка пойти не может.", True),
    ("Конь b1 не может пойти на c3.", True),
    ("Слон c4 не может пойти на f7, там пешка под защитой короля.", False),  # a capture that costs, not a rule
    ("Если слон уйдёт, конь не может пойти на d4.", False),
    ("Пешка b2 не может пойти на b5.", False),
])
def test_a_legal_move_denied(sentence, caught):
    assert bool(check_sentence(sentence, CheckContext.from_fens([START4]))) is caught


def test_the_castling_rule_named_in_the_question_only():
    ctx = CheckContext.from_fens(["4k2r/8/8/8/8/8/8/4K2R w K - 0 1"], question="Можно рокироваться, если ладья под боем?")
    assert check_sentence("Можно, если только ваша ладья не находится под боем.", ctx)
    assert check_sentence("Нет, при атакованной ладье рокировка запрещена.", ctx)
    assert check_sentence("Да, можно: даже если ладья под боем, рокировка разрешена.", ctx) == []


def test_a_wrong_no_to_the_castling_rule_question():
    ctx = CheckContext.from_fens([chess.STARTING_FEN], question="Можно ли рокироваться, если моя ладья под боем?")
    assert check_sentence("Нет, нельзя — рокировка через битое поле запрещена.", ctx)
    assert check_sentence("Нет, ладья под боем рокировке не мешает.", ctx) == []


@pytest.mark.parametrize("text,out", [
    ("Затем выводи короля из-под пешки, а ладью поставь на четвёртую.", "Выводи короля из-под пешки, а ладью поставь на четвёртую."),
    ("**Затем** выводи короля из-под пешки.", "Выводи короля из-под пешки."),
    ("Затяни узел потуже.", "Затяни узел потуже."),
])
def test_a_sentence_leaning_on_one_left_out(text, out):
    from src.answer_check import strip_leaning_start

    assert strip_leaning_start(text) == out


@pytest.mark.parametrize("fen,sentence,caught", [
    ("3R1rk1/6pp/3Q4/pp2Pq2/4Nn2/P7/1P6/K7 w - - 0 1", "Первый ход — **...Rxf3!**.", True),  # a lesson diagram's move
    ("3R1rk1/6pp/3Q4/pp2Pq2/4Nn2/P7/1P6/K7 w - - 0 1", "Первый ход — **Nf6+**.", False),
    ("r1b2rk1/ppp2ppp/1bnq1n2/1B1p2B1/3PP3/2N2N2/PP3PPP/R2Q1RK1 w - - 0 1", "Первый ход — **1...Ba6!**", True),
    (chess.STARTING_FEN, "Первый ход — e4: пешка занимает центр.", False),
])
def test_the_announced_first_move_is_a_move_of_the_board(fen, sentence, caught):
    assert bool(check_sentence(sentence, CheckContext.from_fens([fen]))) is caught


def test_the_only_reply_to_a_sacrifice_is_a_fact():
    from src.position_facts import _forced_replies

    board = chess.Board("r1b4k/pp1n2p1/1qp1B1Pp/2p2p2/3P4/2Q1P3/PP1K1PP1/R6R w - - 0 1")
    move = board.parse_san("Rxh6+")
    after = board.copy()
    after.push(move)
    assert _forced_replies(board, move, after) == "after Rxh6+, Black has only one legal move: gxh6 — it must take the rook on h6"


def test_a_pawn_capture_in_the_question_is_read_not_a_crash():
    fen = "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
    assert [m["san"] for m in question_moves("Почему не exd5?", fen) if m.get("legal")] == ["exd5"]
    assert [m["san"] for m in question_moves("А если b3?", fen) if m.get("legal")] == ["b3"]
