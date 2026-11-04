"""voice 03.11 reviews (review-fp, review-miss, review-facts of voice-1102 at 48853346): the classes they found, on
boards and wordings of their own (none of the reviewers' boards), positive and negative, said aloud and written.

* A standing claim told right after a move — in the same sentence («Неплохо конём на g5: он нападает на пешку h7»), in
  the sentence before («Сыграй конём на g5.» → «Конь нападает на пешку h7.») or as another square for that piece («Или
  на b4, тогда он нападает на коня c3») — is about the board after it (answer_check._after_told_move).
* Castling told in words is a move: its own rook and king squares are its result, not a line or a proposal.
* «держит пешку» is not «attacks the pawn»; an empty square «под ударом слона» is judged on the board now, not on the
  starting position the context keeps.
* The engine stage does not judge a move put off or ruled out by its own sentence (_not_now).
* Misses closed: proposal frames shared by the legality check and the engine stage (adverb + infinitive, «обрати
  внимание на ход», a move noun with a nominative piece), a capture with the captured piece named, a check claimed for a
  move or the board now, the verb-first castling reason, castling after a step told in words, a material claim with
  no amount, «король уже ходил» against kept rights.
* The voice note's facts: scoped castling door, «nothing else» only when true, the other side's castling, placement,
  promotions, the game note without «+/#» and pawn structure, relative pins, the check's checker and replies.
"""
from __future__ import annotations

import re

import chess
import pytest
from fastapi.testclient import TestClient

from src import config, server
from src.answer_check import CheckContext, check_sentence, proposed_move

ITALIAN_W = "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
QGD_B = "rnbqkb1r/ppp2ppp/4pn2/3p4/2PP4/2N2N2/PP2PPPP/R1BQKB1R b KQkq - 3 4"
RUY_W = "r1bqkb1r/pppp1ppp/2n2n2/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
FRENCH_W = "rnbqkbnr/pp3ppp/4p3/2ppP3/3P4/8/PPP2PPP/RNBQKBNR w KQkq - 0 4"
LONDON_B = "r3kbnr/pp3ppp/2n1p3/q2p1b2/3P1B2/2P1PN2/PP1N1PPP/R2QKB1R b KQkq - 2 7"
TWO_BISHOPS_W = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 6 5"
Q = "Что мне делать?"


@pytest.fixture(autouse=True)
def _no_limit(monkeypatch):
    async def _none(*a, **k):
        return None

    monkeypatch.setattr(server, "enforce_rate_limit", _none)
    monkeypatch.setattr("src.board_rules.tablebase", lambda board: None)


def _voice(fen, text, previous=None, engine=False):
    body = {"text": text, "fen": fen, "engine": engine, "question": Q}
    if previous:
        body["previous"] = previous
    r = TestClient(server.app).post("/api/coach/voice/check", headers={"X-User-Id": "t1103"}, json=body)
    assert r.status_code == 200
    return r.json()


CASES = [
    # ── a standing claim after a move told just before it ──
    ("told_same+", ITALIAN_W, "Неплохо конём на жэ пять: он нападает на пешку аш семь.", None, False),
    ("told_same_w+", ITALIAN_W, "Неплохо Ng5: он нападает на пешку h7.", None, False),
    ("told_same-", ITALIAN_W, "Неплохо конём на жэ пять: он нападает на пешку дэ семь.", None, True),
    ("told_prev+", ITALIAN_W, "Конь нападает на пешку аш семь.", "Сыграй конём на жэ пять.", False),
    ("told_prev_w+", ITALIAN_W, "Конь нападает на пешку h7.", "Сыграй Ng5.", False),
    ("told_prev-", ITALIAN_W, "Конь нападает на пешку бэ семь.", "Сыграй конём на жэ пять.", True),
    ("now_still-", ITALIAN_W, "Конь нападает на пешку аш семь.", None, True),
    ("told_same_b+", QGD_B, "Хорошо слоном на бэ четыре: он нападает на коня цэ три.", None, False),
    ("told_same_b-", QGD_B, "Хорошо слоном на бэ четыре: он нападает на коня эф три.", None, True),
    ("ell+", QGD_B, "Или на бэ четыре, тогда он нападает на коня цэ три.", "Слон может пойти на дэ шесть.", False),
    ("ell-", QGD_B, "Или на бэ четыре, тогда он нападает на коня эф три.", "Слон может пойти на дэ шесть.", True),
    # ── castling told in words ──
    ("castle_res+", RUY_W, "При рокировке ладья перейдёт на эф один, а король встанет на жэ один.", "Рокируйся в короткую.", False),
    ("castle_res2+", RUY_W, "После рокировки ладья встанет на эф один.", "Рокируйся.", False),
    # ── «держит пешку», an empty square under attack ──
    ("hold_pawn+", FRENCH_W, "Пешка е шесть держит твою пешку е пять.", None, False),
    ("hold_attack-", FRENCH_W, "Пешка е шесть атакует твою пешку е пять.", None, True),
    # held back only by a piece on or hitting the square ahead; a knight that does neither does not hold it
    ("hold_none-", FRENCH_W, "Пешку е пять держит конь жэ восемь.", None, True),
    ("hold_ahead+", FRENCH_W, "Пешку дэ четыре держит пешка цэ пять.", None, False),
    ("empty_sq+", LONDON_B, "Поле бэ восемь под ударом слона.", None, False),
    ("empty_sq2+", LONDON_B, "Поле цэ семь под ударом белого слона.", None, False),
    ("empty_sq-", LONDON_B, "Поле дэ восемь под ударом слона.", None, True),
    # ── a check claimed ──
    ("check+", ITALIAN_W, "Слоном на эф семь — шах, и королю придётся уйти.", None, False),
    ("check-", ITALIAN_W, "Конём на жэ пять — шах.", None, True),
    ("check_w-", ITALIAN_W, "Ng5 — шах.", None, True),
    ("check_with-", ITALIAN_W, "Иди ферзём на е два с шахом.", None, True),
    ("check_no+", ITALIAN_W, "Конём на жэ пять, без шаха, но с угрозой.", None, False),
    ("check_hypo+", ITALIAN_W, "Если бы конь пошёл на жэ пять, был бы шах.", None, False),
    ("check_you-", ITALIAN_W, "Внимание: тебе шах.", None, True),
    ("check_forced+", RUY_W, "Конь вынужден уйти на жэ пять с шахом.", None, False),  # a reply forced in a line
    ("check_then_king-", ITALIAN_W, "Конём на жэ пять — шах, и королю придётся уйти.", None, True),
    # ── a capture with the captured piece named ──
    ("cap_obj+", ITALIAN_W, "Возьми конём пешку на е пять.", None, False),
    ("cap_obj-", ITALIAN_W, "Возьми слоном пешку на е пять.", None, True),
    ("cap_desc+", ITALIAN_W, "Твой конь бьёт пешку на е пять.", None, False),
    # ── proposal frames ──
    ("noun_nom-", ITALIAN_W, "Хороший ход — пешка на е четыре.", None, True),
    ("noun_nom+", ITALIAN_W, "Хороший ход — пешка на дэ три.", None, False),
    ("noun_from+", ITALIAN_W, "Хороший ход — ферзь с дэ один на е два.", None, False),
    ("noun_from-", ITALIAN_W, "Хороший ход — ферзь с дэ два на е два.", None, True),
    ("frame_adv+", ITALIAN_W, "Тут сильно пойти конём на жэ пять.", None, False),
    ("frame_adv-", ITALIAN_W, "Тут сильно пойти слоном на е пять.", None, True),
    ("frame_look-", ITALIAN_W, "Обрати внимание на ход ферзём на дэ четыре, он очень полезный.", None, True),
    # ── castling reasons and castling after a step ──
    ("cr_verbfirst-", RUY_W, "Длинная рокировка пока невозможна: мешает конь на цэ один.", None, True),
    ("cr_verbfirst+", RUY_W, "Длинная рокировка пока невозможна: мешает слон на цэ один.", None, False),
    ("after_words-", RUY_W, "После хода пешкой на дэ три можно будет рокироваться в длинную.", None, True),
    ("after_words+", RUY_W, "После хода пешкой на дэ три можно будет рокироваться в короткую.", None, False),
    ("king_moved-", ITALIAN_W, "Рокировка невозможна, ведь король уже ходил.", None, True),
    # castling advised right after a step: its own pieces still between after it (not an attacked square: the reply decides)
    ("step_castle-", TWO_BISHOPS_W, "Сыграй Nc3 и рокируйся в длинную.", None, True),
    ("step_castle_words-", TWO_BISHOPS_W, "Сыграй конём на цэ три и рокируйся в длинную.", None, True),
    ("step_castle+", TWO_BISHOPS_W, "Сыграй Nc3 и рокируйся в короткую.", None, False),
    ("step_castle_d3+", "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4", "Сыграй d3 и рокируйся.", None, False),
    ("step_castle_attacked+", "r2qk1nr/ppp3pp/3p4/2b1p3/1nP5/3b1NP1/PP1P1PBP/R1BQK2R w KQkq - 0 9",
     "Сыграй h3 и рокируйся в короткую.", None, False),
    # ── material with no amount ──
    ("mat_dir-", ITALIAN_W, "Ты отстаёшь по материалу.", None, True),
    ("mat_eq+", ITALIAN_W, "Материал равный.", None, False),
    ("mat_exch-", ITALIAN_W, "Ты потерял качество.", None, True),
]


@pytest.mark.parametrize("name,fen,text,previous,cut", CASES, ids=[c[0] for c in CASES])
def test_voice_check_classes(name, fen, text, previous, cut):
    got = _voice(fen, text, previous)
    assert bool(got["issues"]) == cut, got["issues"]


def test_chat_reads_the_sentence_before_too():
    """The written answer, sentence by sentence on one context (the text coach's gate): the same mechanism."""
    ctx = CheckContext.from_fens([ITALIAN_W], question=Q)
    assert check_sentence("Сыграй Ng5.", ctx) == []
    assert check_sentence("Конь нападает на пешку h7.", ctx) == []
    ctx = CheckContext.from_fens([ITALIAN_W], question=Q)
    assert check_sentence("Сыграй Ng5.", ctx) == []
    assert check_sentence("Конь нападает на пешку b7.", ctx)


def test_after_told_move_switch(monkeypatch):
    monkeypatch.setenv("COACH_DETECTORS_OFF", "after_told_move")
    assert _voice(ITALIAN_W, "Конь нападает на пешку аш семь.", "Сыграй конём на жэ пять.")["issues"]


def test_lesson_reading_unchanged():
    """The lesson tutor's context reads as before: no re-judging after a told move."""
    ctx = CheckContext.from_fens([ITALIAN_W], question=Q)
    ctx.relation_surface = "lesson"
    check_sentence("Сыграй Ng5.", ctx)
    assert ctx.told_before == []


# ── the engine stage: what it is asked ──
@pytest.mark.parametrize("text,want", [
    ("Можно конём на жэ пять.", "Ng5"),
    ("После короткой рокировки можно конём на жэ пять.", None),
    ("Конём на жэ пять сейчас рано.", None),
    ("Конь может прыгнуть на жэ пять, но сейчас это рано.", None),
    ("Сначала рокируйся, а потом можно конём на жэ пять.", None),
    ("Рокируйся: ладья встанет на эф один.", None),
    ("Ферзём на е два нападать не стоит.", None),
    ("Давай конём на жэ пять.", "Ng5"),
    ("Тут сильно пойти конём на жэ пять.", "Ng5"),
    ("Обрати внимание на ход конём на жэ пять, он полезный.", "Ng5"),
    ("Хороший ход — пешка на дэ три.", "d3"),
    ("Возьми конём пешку на е пять.", "Nxe5"),
])
def test_proposed_move_reading(text, want):
    from src.game_intent import spoken_squares

    ctx = CheckContext.from_fens([ITALIAN_W], question=Q)
    got = proposed_move(spoken_squares(text), ctx)
    assert (got[2] if got else None) == want


def test_engine_stage_gets_spoken_word_frames(monkeypatch):
    calls = []

    def _move(board, move, san, *a, **k):
        calls.append(san)
        return f"{san} is a mistake (stub)"

    monkeypatch.setattr(config, "COACH_MOVE_VERIFY", True)
    monkeypatch.setattr("src.hypothetical.verify_recommendation", _move)
    for text in ("Двинь пешку на дэ четыре.", "Давай переведём коня на жэ пять."):
        calls.clear()
        out = _voice(ITALIAN_W, text, engine=True)
        assert calls and out["issues"], (text, out)
    calls.clear()
    assert not _voice(ITALIAN_W, "Конём на жэ пять сейчас рано.", engine=True)["issues"] and not calls


# ── the voice note's facts ──
def _rules(fen, game=False):
    from src.board_rules import rule_facts

    return rule_facts(chess.Board(fen), with_tablebase=False, explicit=True, game=game)


def test_castling_door_scoped_and_without_unsafe_pieces():
    # the rook a1 hangs to Qa3xa1: its square is never in the castling clause
    text = " ".join(_rules("r3k1nr/ppp2ppp/2n1p3/3p1b2/3P1B2/q1Q5/1PP1PPPP/R3KBNR w KQkq - 0 9"))
    assert "does not matter" not in text
    assert "a1" not in text.split("castling depends only on")[1].split(";")[0] if "castling depends only on" in text else True


def test_between_pieces_names_the_attacked_landing_square():
    text = " ".join(_rules("r3k2r/pppq1ppp/2n5/2b5/8/2N5/PPPQ2PP/R3K1NR w KQkq - 0 10"))
    assert "nothing else stands there" not in text
    assert "g1, which the black bishop on c5 attacks" in text


def test_castling_said_when_both_wings_are_own_blocked_and_when_the_king_left():
    assert any("short castling (O-O) is NOT possible now" in f
               for f in _rules("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"))
    assert any("the king has left e1" in f for f in _rules("rnbq1bnr/ppppkppp/8/4p3/4P3/8/PPPPKPPP/RNBQ1BNR w - - 2 3"))
    assert any(f.startswith("Black (on its next move): O-O barred — f8 is attacked by the white bishop on a3")
               for f in _rules("rnbqk2r/pppp1pbp/5np1/4p3/8/BPN1PN2/P1PP1PPP/R2QKB1R w KQkq - 0 1"))


def test_placement_promotions_and_no_move_wording():
    facts = _rules("4k3/2P5/8/8/8/8/5K2/8 w - - 0 60")
    assert any("c8=Q+ (or =R, =B, =N)" in f for f in facts)
    assert any(f.startswith("Pieces on the board — White: Kf2; pawns c7. Black: Ke8; no pawns") for f in facts)
    assert any("the queen d1 has no legal move now" in f for f in _rules("b3k3/8/8/8/8/8/PPPPPP1P/RNBQK2R w KQ - 0 20"))


def test_game_note_has_no_check_marks_and_no_structure():
    game = " ".join(_rules("6k1/5ppp/8/8/8/8/Q4PPP/3Q2K1 w - - 0 35", game=True))
    assert "#" not in game and "+" not in game and "pawn structure" not in game
    assert "Qd8" in game
    assert any("#" in f for f in _rules("6k1/5ppp/8/8/8/8/Q4PPP/3Q2K1 w - - 0 35"))  # the engine note keeps the marks


def test_chased_attacker_told_as_the_opponents_and_the_block():
    text = " ".join(_rules("4k3/8/8/8/8/3b1B2/8/4K2R w K - 0 1"))
    assert "the black bishop on d3 could retreat to" in text and "it can step to" not in text
    assert "after Be2 O-O becomes legal" in text


def test_relative_pins_and_check_replies():
    from src.position_facts import dynamic_facts, static_facts

    pins = static_facts(chess.Board("rnbqkb1r/ppp2ppp/4pn2/3p2B1/2PP4/2N5/PP2PPPP/R2QKBNR b KQkq - 1 4"), explicit=True)
    assert "the black knight f6 is pinned to the black queen d8: if it moves, Bxd8 takes the queen" in pins
    assert not any("pinned to the black queen" in f for f in static_facts(
        chess.Board("rnbqkb1r/ppp2ppp/4pn2/3p2B1/2PP4/2N5/PP2PPPP/R2QKBNR b KQkq - 1 4")))  # off: as before
    told = dynamic_facts(chess.Board("4r1k1/5ppp/8/8/8/8/5PPP/R3K2R w KQ - 0 22"), None, 0.0, lambda f: {}, explicit=True)
    assert told[0].startswith("White is in check from the black rook e8") and "Kd1" in told[0]


def test_lesson_facts_unchanged():
    from src.board_rules import castling_facts, rule_facts

    plain = rule_facts(chess.Board("r3k2r/pppq1ppp/2n5/2b5/8/2N5/PPPQ2PP/R3K1NR w KQkq - 0 10"), with_tablebase=False)
    assert not any("Pieces on the board" in f for f in plain)
    assert castling_facts(chess.Board("rnbq1bnr/ppppkppp/8/4p3/4P3/8/PPPPKPPP/RNBQ1BNR w - - 2 3")) == []


# ── castling state of a named side, castling told after a step, «Когда рокироваться?» (review-miss 03.11, round 3) ──
ITALIAN_B_OO_W = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQ1RK1 b kq - 1 5"  # White castled, Black at home
KNIGHTS_W = "rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
VIENNA_W = "rnbqkb1r/pppp1ppp/5n2/4p3/4P3/2N5/PPPP1PPP/R1BQKBNR w KQkq - 2 3"
KING_WALKED_B = "r1bq3r/ppppkppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQ1RK1 b - - 3 6"
STATE_CASES = [
    ("castled_you-", ITALIAN_B_OO_W, "Ты уже рокировался, теперь думай о центре.", Q, True),
    ("castled_black-", ITALIAN_B_OO_W, "Чёрные уже рокировались.", Q, True),
    ("castled_white+", ITALIAN_B_OO_W, "Белые уже рокировались.", Q, False),
    # two sides in one sentence: each claim with its own clause's subject (proof 03.11, london-black-14)
    ("castled_contrast+", ITALIAN_B_OO_W, "Белые уже рокировались, а ты ещё нет.", Q, False),
    ("castled_contrast-", ITALIAN_B_OO_W, "Ты уже рокировался, а белые ещё нет.", Q, True),
    ("castled_contrast_true+", "r1bq1rk1/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQ - 1 6",
     "Соперник уже рокировался, а ты ещё нет.", Q, False),
    ("castled_opp+", ITALIAN_B_OO_W, "Соперник уже рокировался.", Q, False),
    ("castled_not+", ITALIAN_B_OO_W, "Ты ещё не рокировался.", Q, False),
    ("castled_hypo+", ITALIAN_B_OO_W, "Если бы ты уже рокировался, конь был бы не страшен.", Q, False),
    ("castled_nosubj+", ITALIAN_B_OO_W, "Король уже спрятан рокировкой.", Q, False),
    ("still_white-", ITALIAN_B_OO_W, "Белые ещё могут рокироваться.", Q, True),
    ("still_opp+", ITALIAN_B_OO_W, "Соперник ещё может рокироваться в короткую.", Q, False),
    ("still_you+", ITALIAN_B_OO_W, "Ты ещё можешь рокироваться в короткую.", Q, False),
    ("nolonger_black-", ITALIAN_B_OO_W, "Чёрные уже не могут рокироваться в короткую.", Q, True),
    ("nolonger_white+", ITALIAN_B_OO_W, "Белые уже не могут рокироваться.", Q, False),
    ("nolonger_q+", ITALIAN_B_OO_W, "Чёрные уже не могут рокироваться?", Q, False),
    ("then_long-", KNIGHTS_W, "Сначала конём на цэ три, а потом сразу рокировка в длинную.", Q, True),
    ("then_short+", KNIGHTS_W, "Сначала пешкой на дэ три, а потом рокировка в короткую.", Q, False),
    ("then_imp-", KNIGHTS_W, "Сначала конём на цэ три, а потом сразу рокируйся в длинную.", Q, True),
    ("then_imp_plan+", KNIGHTS_W, "Сначала конём на цэ три, а потом рокируйся в длинную.", Q, False),
    # a plan with «затем»: the knight g1 goes out on the way (replay_live 03.11, name-kid)
    ("then_plan+", VIENNA_W, "Дальше спокойно доразвиваешься: слоном на цэ четыре, а затем короткая рокировка.", Q, False),
    ("then_at_once-", VIENNA_W, "Сначала слоном на цэ четыре, а потом сразу рокировка в короткую.", Q, True),
    ("then_nostep+", KNIGHTS_W, "Потом рокировка в длинную.", Q, False),
    ("then_if+", KNIGHTS_W, "Если сначала конём на цэ три, то потом рокировка в длинную.", Q, False),
    ("ready_short+", KNIGHTS_W, "Освободи место: конём на цэ три, и короткая рокировка готова.", Q, False),
    ("ready_long-", KNIGHTS_W, "Освободи место: конём на цэ три, и длинная рокировка готова.", Q, True),
    ("ready_nostep+", KNIGHTS_W, "Длинная рокировка будет готова через пару ходов.", Q, False),
    ("when_q-", KING_WALKED_B, "Самое время рокироваться в короткую.", "Когда мне рокироваться?", True),
    ("when_if+", KING_WALKED_B, "Самое время рокироваться в короткую.", "А если я уведу слона, когда можно рокироваться?", False),
    ("when_legal+", ITALIAN_B_OO_W, "Самое время рокироваться в короткую.", "Когда рокироваться?", False),
]


@pytest.mark.parametrize("name,fen,text,question,cut", STATE_CASES, ids=[c[0] for c in STATE_CASES])
def test_castling_state_and_steps(name, fen, text, question, cut):
    from src.game_intent import spoken_squares

    r = TestClient(server.app).post("/api/coach/voice/check", headers={"X-User-Id": "t1103"},
                                    json={"text": text, "fen": fen, "engine": False, "question": question})
    assert bool(r.json()["issues"]) == cut, r.json()["issues"]
    # the written answer is read the same way
    ctx = CheckContext.from_fens([fen], question=question)
    assert bool(check_sentence(spoken_squares(text), ctx)) == cut


def test_castle_state_switch(monkeypatch):
    monkeypatch.setenv("COACH_DETECTORS_OFF", "castle_state")
    assert not _voice(ITALIAN_B_OO_W, "Чёрные уже рокировались.")["issues"]


# ── the voice note's facts as properties, on 40 positions of seeded random games (none of the reviewers' boards) ──
def _random_board(seed: int) -> chess.Board:
    import random

    rnd, board = random.Random(seed), chess.Board()
    for _ in range(10 + seed % 30):
        moves = list(board.legal_moves)
        if not moves or board.is_game_over():
            break
        board.push(rnd.choice(moves))
    return board


_SEEDED = [b for b in (_random_board(s) for s in range(7001, 7041)) if not b.is_game_over()]
_PIECE_LETTER = {chess.KING: "K", chess.QUEEN: "Q", chess.ROOK: "R", chess.BISHOP: "B", chess.KNIGHT: "N"}


@pytest.mark.parametrize("board", _SEEDED, ids=[b.fen() for b in _SEEDED])
def test_voice_facts_properties(board):
    facts = _rules(board.fen())
    text = " ".join(facts)
    # placement: every piece where it stands, nothing else
    place = next(f for f in facts if f.startswith("Pieces on the board"))
    for colour, name in ((chess.WHITE, "White"), (chess.BLACK, "Black")):
        part = place.split(f"{name}: ", 1)[1].split(". Black:", 1)[0] if name == "White" else place.split("Black: ", 1)[1]
        want = {f"{_PIECE_LETTER[p.piece_type]}{chess.square_name(s)}" for s, p in board.piece_map().items()
                if p.color == colour and p.piece_type != chess.PAWN}
        pawns = {chess.square_name(s) for s in board.pieces(chess.PAWN, colour)}
        got = set(re.findall(r"\b[KQRBN][a-h][1-8]\b", part.split("pawns")[0]))
        assert got == want
        assert set(re.findall(r"\b[a-h][1-8]\b", part.split("pawns", 1)[1] if "pawns" in part else "")) == pawns
    # «nothing else stops it»: true — with the pieces between gone, that castling is legal
    for fact in facts:
        if not fact.startswith(("White: ", "Black: ")):
            continue
        colour = chess.WHITE if fact.startswith("White") else chess.BLACK
        for clause in fact.split("; "):
            if "nothing else stops it" not in clause:
                continue
            wing = "O-O-O" if "O-O-O" in clause else "O-O"
            rank = 0 if colour == chess.WHITE else 7
            empty = board.copy(stack=False)
            empty.turn = colour
            empty.ep_square = None
            for f in ((5, 6) if wing == "O-O" else (1, 2, 3)):
                empty.remove_piece_at(chess.square(f, rank))
            king = chess.Move(chess.square(4, rank), chess.square(6 if wing == "O-O" else 2, rank))
            assert empty.is_legal(king), clause
    # the door: no square of a piece told as not defended
    for door in re.findall(r"an attack on ([a-h1-8, or]+) does not stop it", text):
        for sq in re.findall(r"[a-h][1-8]", door):
            assert f"{sq} is attacked" not in text and not re.search(rf"\b{sq}\b[^;]*not defended", text)
    # the game note: no check or mate marks
    game = " ".join(_rules(board.fen(), game=True))
    assert "+" not in game and "#" not in game


def test_lesson_reads_castling_words_as_before():
    """The castling result reading (review-fp 03.11) stays out of the lesson tutor: its context reads as on 48853346."""
    text = "После рокировки ладья перейдёт на f1, а король на g1."
    ctx = CheckContext.from_fens([RUY_W], question=Q)
    assert check_sentence("Рокируйся в короткую.", ctx) == [] and check_sentence(text, ctx) == []
    ctx = CheckContext.from_fens([RUY_W], question=Q)
    ctx.relation_surface = "lesson"
    check_sentence("Рокируйся в короткую.", ctx)
    assert check_sentence(text, ctx)  # the lesson's old reading: a rook-move line
