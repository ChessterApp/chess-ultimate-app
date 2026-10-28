"""The coach's castling said in words is checked against the engine's last move (28.10).

«Я рокируюсь», «Мой ход — рокировка», "I castle" passed the game check whatever the engine had played,
and «Мой ход — король на g8, рокировка» was flagged when the engine had castled (O-O named no square).
"""
import pytest

from src.answer_check import CheckContext, check_sentence
from src.move_text import spoken_squares

A = ["e5", "Nc6", "a6"]                   # last a6
K = ["e5", "Nc6", "Bc5", "Nf6", "O-O"]    # last short castle
L = ["d5", "Nc6", "Bg4", "Qd7", "O-O-O"]  # last long castle
N = ["e5", "Nf6", "Nxe4"]                 # last knight capture


def _claimed_wrongly(played, sentence):
    ctx = CheckContext.from_fens()
    ctx.game_engine_moves = played
    return any("engine plays your moves" in i for i in check_sentence(spoken_squares(sentence), ctx))


@pytest.mark.parametrize("played,sentence", [
    (A, "Я рокируюсь."),
    (A, "Мой ход — рокировка."),
    (A, "I castle."),
    (A, "Я делаю рокировку."),
    (A, "Мой ход — короткая рокировка."),
    (N, "Я рокируюсь, король уходит в безопасность."),
    (K, "Мой ход — длинная рокировка."),
    (L, "Я делаю короткую рокировку."),
    (K, "I castle queenside."),
    (L, "I castle kingside."),
    (A, "My move is castling."),
    (K, "Я рокируюсь в длинную сторону."),
])
def test_castling_the_engine_did_not_just_play_is_caught(played, sentence):
    assert _claimed_wrongly(played, sentence)


@pytest.mark.parametrize("played,sentence", [
    (K, "Мой ход — рокировка."),
    (K, "Я делаю рокировку."),
    (K, "Я рокируюсь."),
    (K, "Мой ход — короткая рокировка, король в безопасности."),
    (K, "Мой ход — король на g8, рокировка."),
    (K, "Я делаю ход королём на g8 — это рокировка."),
    (K, "I castle kingside."),
    (K, "My move is castling."),
    (K, "I castle: king to g8."),
    (L, "Я делаю длинную рокировку, король на c8."),
    (L, "Мой ход — длинная рокировка."),
    (L, "I castle queenside."),
    (L, "I castle long."),
    # lines, intentions, negations: not «my move now»
    (A, "Если ты сыграешь Ba4, я рокируюсь."),
    (A, "Я не рокируюсь, рано."),
    (A, "Скоро я рокируюсь."),
    (A, "Я хочу рокироваться."),
    (A, "I can't castle yet."),
    (A, "When you play Ba4, I castle."),
    (A, "I'll castle next."),
    (A, "Мой план — рокировка и d6."),
    (L, "Я рокируюсь в длинную сторону."),
    (A, "Я рокируюсь, если есть время."),
    (A, "I castle when the centre is closed."),
    (A, "В этой дебютной схеме я рокируюсь в короткую сторону."),
    (A, "Мой ход — рокировка? Нет, a6."),
])
def test_a_true_castling_or_a_line_passes(played, sentence):
    assert not _claimed_wrongly(played, sentence)
