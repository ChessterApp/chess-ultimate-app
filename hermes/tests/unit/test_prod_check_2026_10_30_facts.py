"""Prod check 29.10 → 30.10: claims the board and the game's record decide exactly (src/answer_check_facts.py).

* st2 (text game, the student Black): «Так что сейчас надо в первую очередь увести ферзя с d8 — например, на c7 или
  на b6» after 5.fxe7 — c7 holds Black's own pawn, d8–b6 is shut by it; the queen's only move is Qxe7.
* attacked («Что у меня сейчас под ударом?»): the answer named the bishop c4 only; the d5 pawn, hit by Nf6 and Qd8 and
  held only by that bishop, was listed in the coach's facts as «defended» — the facts now say it is not safe, and
  «под ударом только …», «больше ничего не висит» are read against them.
* move-najdorf: «Это … конкретно система, где белые пошли 6.Сс4» on the board after 5...a6 (the bishop on f1).
* name-scandi: «Чёрные рано вывели ферзя на d5 после размена на e4» after 1.e4 d5 2.exd5 Qxd5.

Each class with paraphrases, and the sentences that must pass: plans, conditions, questions, denials, quotes, other
games, the truth."""

import chess
import pytest
from fastapi.testclient import TestClient

from src.answer_check import CheckContext, check_sentence
from src.position_facts import exchange_gain, exposed_pieces, static_facts
from src.prompt_builder import board_facts_block

ST2_MOVES = "d4 e5 dxe5 Nc6 Nf3 Nf6 exf6 Be7 fxe7".split()
ST2_PGN = "1. d4 e5 2. dxe5 Nc6 3. Nf3 Nf6 4. exf6 Be7 5. fxe7"
ATTACKED = "r1bqkb1r/ppp2ppp/5n2/n2Pp1N1/2B5/8/PPPP1PPP/RNBQK2R w KQkq - 1 6"
NAJDORF = "rnbqkb1r/1p2pppp/p2p1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 0 6"
SCANDI = "rnb1kbnr/ppp1pppp/8/3q4/8/8/PPPP1PPP/RNBQKBNR w KQkq - 0 3"
# 4.Bb5 with d7–d6 played: the knight c6 is pinned to the king e8.
PINNED = "r1bqkbnr/ppp2ppp/2np4/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 0 4"

PROD_ADVICE = "Так что сейчас надо в первую очередь увести ферзя с d8 — например, на c7 или на b6, подальше от этой пешки."
PROD_NAJDORF = "Это сицилианская защита, вариант Найдорфа — конкретно система, где белые пошли 6.Сс4 (вариант Фишера-Созина)."
PROD_SCANDI = "Чёрные рано вывели ферзя на d5 после размена на e4 — характерный признак этой системы."


def _st2_fen() -> str:
    board = chess.Board()
    for san in ST2_MOVES:
        board.push_san(san)
    return board.fen()


def _game(student=chess.BLACK, question="0-0"):
    """The st2 game as the text coach sees it: the board, its PGN as a line, the record, the student's colour."""
    ctx = CheckContext.from_fens([_st2_fen()], [ST2_PGN], question=question, student_color=student)
    ctx.game_moves = list(ST2_MOVES)
    first = 0 if student == chess.WHITE else 1
    ctx.game_engine_moves = [m for i, m in enumerate(ST2_MOVES) if i % 2 != first]
    return ctx


def _study(fen, question=""):
    return CheckContext.from_fens([fen], question=question)


# ── (a) a move advised in words that the piece cannot make ────────────────────────────────────────────────────

@pytest.mark.unit
def test_the_production_advice_is_caught_with_the_legal_move():
    issues = check_sentence(PROD_ADVICE, _game())
    assert issues, issues
    text = " ".join(issues)
    assert "black queen on d8 cannot go to c7" in text and "b6" in text
    assert "a black pawn stands on c7" in text and "the pawn on c7 is in the way" in text
    assert "its only legal move now is Qxe7" in text


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Уведи ферзя на c7.",
    "Ферзя надо увести на b6.",
    "Отступи ферзём на c7 или b6.",
    "Сейчас поставь ферзя на c7.",
    "Ферзю сейчас надо уйти на c7.",
    "Retreat the queen to c7.",
    "Нужно срочно отвести ферзя с d8 на b6.",
])
def test_paraphrases_of_the_impossible_advice(sentence):
    issues = check_sentence(sentence, _game())
    assert any("queen on d8 cannot go to" in i for i in issues), issues


@pytest.mark.unit
def test_the_coachs_own_piece_is_judged_too():
    # The student White, the coach Black: «я уведу ферзя с d8 на c7» names an impossible move all the same.
    issues = check_sentence("Сейчас я уведу ферзя с d8 на c7.", _game(student=chess.WHITE))
    assert any("black queen on d8 cannot go to c7" in i for i in issues), issues


@pytest.mark.unit
def test_the_piece_of_the_side_not_to_move_is_judged_after_any_reply():
    # White to move: Black's queen d5 cannot reach f7 (its own pawn) whatever White plays.
    issues = check_sentence("Чёрным сейчас надо увести ферзя на f7.", _study(SCANDI))
    assert any("black queen on d5 cannot go to f7" in i for i in issues), issues
    # …while a5 and d6 are open to it after any quiet reply.
    assert check_sentence("Можно увести ферзя на a5 или d6.", _study(SCANDI)) == []


@pytest.mark.unit
def test_a_pinned_piece_cannot_go():
    issues = check_sentence("Уведи коня с c6 на d4.", _study(PINNED))
    assert any("knight on c6 cannot go to d4 (it would leave its own king in check)" in i for i in issues), issues
    assert check_sentence("Сейчас уведи коня на e7.", _study(PINNED)) == []  # the g8 knight can


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Можно увести ферзя на e7.",                                         # Qxe7 — legal
    "Если бы пешки c7 не было, ферзя можно было бы увести на c7.",      # a condition
    "Сначала сыграй c6, потом уведи ферзя на c7.",                       # a plan of two moves
    "Увести ферзя на c7 нельзя: там стоит пешка.",                       # the truth, denied
    "Куда увести ферзя — на c7 или на b6?",                              # a question to the student
    "Ты хочешь увести ферзя на c7, но там твоя пешка.",                  # the student's idea
    "«Уведи ферзя на c7» — так ты написал.",                             # quoted
    "План — поставить коня на d5.",                                      # a plan, not this move
    "Правильно было отступить ферзём на c7.",                            # about a move gone by (corpus 30.10)
    "Подумай, какое поле для ферзя заодно прикрывает твоего короля.",
])
def test_advice_that_is_not_a_claim_about_this_move_passes(sentence):
    assert not [i for i in check_sentence(sentence, _game()) if "cannot go to" in i]


@pytest.mark.unit
def test_advice_legal_in_a_position_a_tool_gave_passes():
    ctx = _game()
    # A lesson diagram the tool showed, with the c7 pawn gone: «уведи ферзя на c7» may be about it.
    ctx.add_text('{"fen": "rnbqk2r/pp1pPppp/8/8/8/8/PPP1PPPP/RNBQKB1R b KQkq - 0 5"}')
    assert not [i for i in check_sentence("Уведи ферзя на c7.", ctx) if "cannot go to" in i]


# ── (b) «what is attacked» answered as if complete ───────────────────────────────────────────────────────────

@pytest.mark.unit
def test_the_facts_say_the_d5_pawn_is_not_safe():
    board = chess.Board(ATTACKED)
    facts = static_facts(board)
    d5 = next(f for f in facts if f.startswith("the white pawn d5"))
    assert "defended only by the white bishop c4" in d5 and "NOT safe" in d5
    assert "itself attacked and not safe" in d5  # its defender is hit by the knight a5
    assert facts.index(d5) < next(i for i, f in enumerate(facts) if "pawn h7" in f)  # before the safe ones
    assert exchange_gain(board, chess.D5) == 1 and exchange_gain(board, chess.H7) == 0
    assert {chess.square_name(sq) for sq, *_ in exposed_pieces(board, chess.WHITE)} == {"c4", "d5"}
    assert "NOT safe" in board_facts_block(ATTACKED)


@pytest.mark.unit
def test_an_exchange_lost_only_through_an_xray_counts_and_a_pinned_attacker_does_not():
    # The queen d1 behind the rook d2: Black's knight d5, held by the rook d8, is lost — Rxd5 Rxd5 Qxd5.
    xray = chess.Board("3rk3/8/8/3n4/8/8/3R4/3QK3 w - - 0 1")
    assert exchange_gain(xray, chess.D5) == 3
    assert any(sq == chess.D5 and kind == "outnumbered" for sq, kind, *_ in exposed_pieces(xray, chess.BLACK))
    # The knight e5 «attacks» the rook d7 but is pinned to its king by the queen e8: the rook is safe.
    pinned = chess.Board("4q2k/3R4/8/4N3/8/8/8/4K3 w - - 0 1")
    assert exchange_gain(pinned, chess.D7) == 0


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Под ударом у тебя только слон c4.",
    "Единственная фигура под ударом — слон c4.",
    "Only the bishop on c4 is hanging.",
    "Кроме слона c4, у тебя ничего не висит.",
])
def test_an_exhaustive_claim_that_leaves_d5_out_is_caught(sentence):
    issues = check_sentence(sentence, _study(ATTACKED, "Что у меня сейчас под ударом?"))
    assert any("white pawn d5" in i and "wins material" in i for i in issues), issues


@pytest.mark.unit
@pytest.mark.parametrize("follow", ["Больше ничего не висит.", "Остальное в безопасности.", "Nothing else is hanging."])
def test_nothing_else_after_the_production_sentence_is_caught(follow):
    ctx = _study(ATTACKED, "Что у меня сейчас под ударом?")
    first = "Под ударом у тебя белый слон на c4 — его атакует конь с a5, и он ничем не защищён."
    assert check_sentence(first, ctx) == []  # the production sentence itself claims nothing exhaustive
    issues = check_sentence(follow, ctx)
    assert any("white pawn d5" in i for i in issues), issues


@pytest.mark.unit
@pytest.mark.parametrize("sentences", [
    ["Под ударом у тебя не только слон c4, но и пешка d5."],
    ["Под ударом у тебя только слон c4 и пешка d5."],
    ["Под ударом у тебя слон c4.", "Остальное защищено."],   # d5 is defended — not safe, but defended
    ["Под ударом у тебя слон c4.", "После Bb5+ больше ничего не висит."],  # a line
    ["Больше ничего не висит."],                              # nothing named before: «else» is not known
    ["У чёрных ничего не висит."],                            # true: f7 and h7 are held
    ["А вот если под боем только ладья, рокироваться можно."],  # a rule, conditional
])
def test_true_partial_or_conditional_claims_pass(sentences):
    ctx = _study(ATTACKED, "Что у меня сейчас под ударом?")
    for sentence in sentences:
        assert not [i for i in check_sentence(sentence, ctx) if "under attack on the board" in i], sentence


# ── (c) a move told as played on this board ───────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_the_production_sozin_claim_is_caught():
    issues = check_sentence(PROD_NAJDORF, _study(NAJDORF, "Какие главные теоретические продолжения за белых здесь?"))
    assert any(i.startswith("6.Bc4 has not been played on this board") and "5.Nc3 a6" in i for i in issues), issues


@pytest.mark.unit
@pytest.mark.parametrize("sentence,wrong", [
    ("Здесь белые сыграли 6.Bc4.", "6.Bc4 has not been played"),
    ("В этой позиции чёрные ответили 5...e5.", "Black played a6 here, not e5"),
])
def test_paraphrases_of_a_move_not_played(sentence, wrong):
    issues = check_sentence(sentence, _study(NAJDORF, "Какие продолжения здесь?"))
    assert any(wrong in i for i in issues), issues


@pytest.mark.unit
def test_in_a_game_the_record_decides():
    issues = check_sentence("В этой партии ты сыграл 2...d6.", _game())
    assert any("Black played Nc6 here, not d6" in i for i in issues), issues
    assert check_sentence("Белые только что пошли 5.fxe7.", _game()) == []


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "В системе Созина белые идут 6.Bc4.",                      # the system in general
    "В партии Фишер — Спасский белые пошли 6.Bc4.",            # another game
    "Здесь белые сыграли 5.Nc3.",                               # true
    "Это вариант Найдорфа: чёрные сыграли 5...a6.",             # true
    "Если белые пошли 6.Bc4, то чёрные играют e6.",             # a condition
])
def test_general_true_and_other_game_claims_pass(sentence):
    assert not [i for i in check_sentence(sentence, _study(NAJDORF, "Какие продолжения здесь?"))
                if "played" in i], sentence


@pytest.mark.unit
def test_a_position_a_tool_showed_may_be_the_one_told():
    ctx = _study(NAJDORF, "Что тут было?")
    ctx.add_text('{"fen": "rnbqkb1r/1p2pppp/p2p1n2/8/2BNP3/2N5/PPP2PPP/R1BQK2R b KQkq - 1 6"}')
    assert not [i for i in check_sentence("Здесь белые только что сыграли 6.Bc4.", ctx) if "not been played" in i]


@pytest.mark.unit
def test_a_board_with_no_known_history_is_not_judged():
    # A middlegame FEN with no game, no line, no book line: what was played is unknown.
    ctx = _study("r3k2r/pp3ppp/2n1b3/3q4/8/2N5/PPP2PPP/R2QKB1R w KQkq - 0 10", "Что здесь было?")
    assert check_sentence("Здесь белые сыграли 9.Bc4.", ctx) == []
    assert check_sentence("Чёрные рано вывели ферзя на d5 после размена на e4.", ctx) == []


# ── (d) the history of exchanges ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_the_production_scandinavian_exchange_is_caught():
    ctx = _study(SCANDI, "Как называется этот дебют?")
    assert check_sentence("Это скандинавская защита, вариант Миеса-Котрока (ECO B01).", ctx) == []
    issues = check_sentence(PROD_SCANDI, ctx)
    assert any("no capture was made on e4" in i and "2.exd5 2...Qxd5 (on d5)" in i for i in issues), issues


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Здесь белые разменялись на e4.",
    "После размена на e4 чёрные сразу вывели ферзя в центр.",
])
def test_paraphrases_of_a_wrong_exchange(sentence):
    issues = check_sentence(sentence, _study(SCANDI, "Как называется этот дебют?"))
    assert any("no capture was made on e4" in i for i in issues), issues


@pytest.mark.unit
def test_in_a_game_the_exchanges_are_the_records():
    issues = check_sentence("В нашей партии после размена на d4 ты вывел коня на c6.", _game())
    assert any("no capture was made on d4" in i and "2.dxe5 (on e5)" in i for i in issues), issues
    assert check_sentence("После размена на e5 ты вывел коня на c6.", _game()) == []


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "После размена на d5 чёрные вывели ферзя в центр.",          # true
    "Можно разменяться на e4.",                                   # a plan
    "После размена на e4 у белых будет лучше.",                   # a line, the future
    "Если бы белые разменялись на e4, ферзь не попал бы на d5.",  # a condition
    "Почему после размена на e4 чёрные вывели ферзя?",            # a question
])
def test_plans_questions_and_the_truth_pass(sentence):
    assert not [i for i in check_sentence(sentence, _study(SCANDI, "Как называется этот дебют?"))
                if "no capture" in i], sentence


# ── the voice path: the same checks on what Gemini Live said ──────────────────────────────────────────────────

@pytest.mark.unit
def test_the_voice_check_reads_the_same_claims():
    client = TestClient(app_())
    user = {"X-User-Id": "voice-facts-user"}
    resp = client.post("/api/coach/voice/check", headers=user,
                       json={"text": PROD_ADVICE, "fen": _st2_fen(), "pgn": ST2_PGN, "question": "0-0"})
    assert resp.status_code == 200
    assert any("queen on d8 cannot go to c7" in i for i in resp.json()["issues"])
    resp = client.post("/api/coach/voice/check", headers=user,
                       json={"text": PROD_SCANDI, "fen": SCANDI, "question": "Как называется этот дебют?"})
    assert any("no capture was made on e4" in i for i in resp.json()["issues"])
    resp = client.post("/api/coach/voice/check", headers=user,
                       json={"text": "Под ударом у тебя только слон c4.", "fen": ATTACKED, "question": "Что у меня под ударом?"})
    assert any("white pawn d5" in i for i in resp.json()["issues"])


def app_():
    from src.server import app

    return app
