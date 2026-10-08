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
