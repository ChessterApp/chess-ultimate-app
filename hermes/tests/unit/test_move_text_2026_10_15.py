"""2026-10-15: one reading of a move for every path (src/move_text.py).

The inventory found 13 readers with different tables; each form below was read by some and not others.
"""

import chess
import pytest

from src.move_text import moves_in, normalize, one_move

AFTER_E4_E5 = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
NXE5 = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 2")
CASTLE = chess.Board("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")


@pytest.mark.parametrize("text,san", [
    ("Nf3", "Nf3"), ("Кf3", "Nf3"), ("Кф3", "Nf3"), ("кф3", "Nf3"), ("конь f3", "Nf3"), ("конь ф3", "Nf3"),
    ("конь на f3", "Nf3"), ("g1-f3", "Nf3"), ("Ng1-f3", "Nf3"), ("g1f3", "Nf3"),
    ("Bc4", "Bc4"), ("Сс4", "Bc4"), ("Cc4", "Bc4"), ("сс4", "Bc4"), ("Сб5", "Bb5"),
    ("слон си четыре", "Bc4"), ("слон це 4", "Bc4"), ("Хорошо, слон c4", "Bc4"), ("Слон, c4", "Bc4"),
    ("d2-d4", "d4"), ("d4", "d4"), ("д4", "d4"),
])
def test_every_spelling_of_a_move(text, san):
    assert one_move(text, AFTER_E4_E5) == san


@pytest.mark.parametrize("text", ["Кхе5", "К:е5", "Nxe5", "кхе5", "конь бьёт e5", "f3:e5"])
def test_a_capture_in_any_spelling(text):
    assert one_move(text, NXE5) == "Nxe5"


@pytest.mark.parametrize("text", ["0-0", "O-O", "О-О"])
def test_castling_with_zeros_or_cyrillic_o(text):
    assert one_move(text, CASTLE) == "O-O"


def test_a_square_said_aloud_and_from_square_to_square():
    assert normalize("е два е четыре") == "e2e4"
    assert one_move("е два е четыре", chess.Board()) == "e4"
    # «а» is a word too: not a square in a longer sentence with no move in it
    assert "а три хода назад" in normalize("я помню, а три хода назад было по-другому")


def test_a_piece_on_its_square_is_a_description_not_a_move():
    assert one_move("конь f3 висит", AFTER_E4_E5) is None
    assert [m["san"] for m in moves_in("ферзь b6 атакует короля?", chess.Board("k7/8/3Q4/8/8/8/8/2K5 w - - 0 1"))] == []


def test_russian_notation_takes_kh_as_a_capture():
    from src.notation import russian_to_san

    assert russian_to_san("4.Кхе5 Кхе5") == "4.Nxe5 Nxe5"


def test_the_answer_check_reads_every_cyrillic_file():
    from src.answer_check import CheckContext, check_sentence

    ctx = CheckContext.from_fens([NXE5.fen()])
    assert check_sentence("Сыграй Кхе5 — конь забирает пешку.", ctx) == []
    assert check_sentence("Сыграй Сб5+ с шахом.", ctx) == ["Bb5+ gives no check"]


def test_question_moves_names_no_extra_move_for_long_notation():
    from src.prompt_builder import question_moves

    fen = AFTER_E4_E5.fen()
    assert [m["san"] for m in question_moves("А если Ng1-f3?", fen)] == ["Nf3"]
    assert [m["san"] for m in question_moves("а если кf3?", fen)] == ["Nf3"]
    assert [m["san"] for m in question_moves("А если слон си четыре?", fen)] == ["Bc4"]
