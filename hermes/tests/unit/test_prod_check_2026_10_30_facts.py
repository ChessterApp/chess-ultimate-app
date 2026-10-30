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


# st1, the earlier game of the same chat on production: a Sicilian where Qc7 and Qb6 are legal for Black.
ST1_MOVES = "e4 c5 Nf3 d6 Bc4 e6 O-O Nf6 d3 h6 h3 Nc6".split()
ST1_PGN = "1. e4 c5 2. Nf3 d6 3. Bc4 e6 4. O-O Nf6 5. d3 h6 6. h3 Nc6"


def _st1_fen() -> str:
    board = chess.Board()
    for san in ST1_MOVES:
        board.push_san(san)
    return board.fen()


@pytest.mark.unit
def test_an_earlier_game_of_the_chat_does_not_make_the_advice_legal():
    # Production keeps every board of the session in the check: the st1 game's end, White to move, has Qc7 and Qb6
    # for Black after any reply — the advice passed in the real session (replay 30.10, st1 then st2).
    ctx = CheckContext.from_fens([_st2_fen(), _st1_fen()], [ST2_PGN, ST1_PGN], question="0-0",
                                 student_color=chess.BLACK)
    ctx.game_moves = list(ST2_MOVES)
    assert not [i for i in check_sentence(PROD_ADVICE, ctx) if "cannot go to" in i]  # as before: «legal somewhere»
    ctx = CheckContext.from_fens([_st2_fen(), _st1_fen()], [ST2_PGN, ST1_PGN], question="0-0",
                                 student_color=chess.BLACK)
    ctx.game_moves = list(ST2_MOVES)
    ctx.other_board_keys = {CheckContext._key(chess.Board(_st1_fen()))}
    assert any("queen on d8 cannot go to c7" in i for i in check_sentence(PROD_ADVICE, ctx))


@pytest.mark.unit
def test_an_earlier_board_counts_outside_a_game_or_when_a_tool_shows_it_again():
    def ctx_(game: bool):
        ctx = CheckContext.from_fens([_st2_fen(), _st1_fen()], [ST2_PGN, ST1_PGN], question="Куда увести ферзя?",
                                     student_color=chess.BLACK)
        ctx.game_moves = list(ST2_MOVES) if game else None
        ctx.other_board_keys = {CheckContext._key(chess.Board(_st1_fen()))}
        return ctx

    assert not [i for i in check_sentence(PROD_ADVICE, ctx_(False)) if "cannot go to" in i]
    ctx = ctx_(True)
    ctx.add_text('{"fen": "%s"}' % _st1_fen())  # a tool put the old game up again this turn
    assert not [i for i in check_sentence(PROD_ADVICE, ctx) if "cannot go to" in i]


@pytest.mark.unit
def test_the_text_turn_leaves_the_earlier_games_board_out(monkeypatch):
    import json
    from unittest.mock import MagicMock, patch

    from src import config
    from src.sessions import session_store
    from src.user_profile import UserProfile

    for name, value in {"COACH_TWO_STAGE": False, "COACH_ENGINE_NOTE": False, "COACH_OPENING_PRESTEP": False,
                        "COACH_HYPOTHETICAL_NOTE": False, "COACH_ANSWER_FIX": False, "COACH_ANSWER_CHECK": True}.items():
        monkeypatch.setattr(config, name, value)
    session = session_store.create(user_id="facts-game-user")
    old = session.add_board(kind="game", pgn=ST1_PGN, fen=_st1_fen())
    old.game_state = {"status": "playing", "moves": list(ST1_MOVES), "student_color": "white"}
    new = session.add_board(kind="game", pgn=ST2_PGN, fen=_st2_fen())
    new.game_state = {"status": "playing", "moves": list(ST2_MOVES), "student_color": "black"}
    session.board_state = _st2_fen()
    draft = PROD_ADVICE + " Это главное сейчас."
    agent = MagicMock()
    agent.tools, agent._api_call_count, agent.max_iterations = [], 1, 5
    agent.session_prompt_tokens = agent.session_completion_tokens = 0

    def chat(message, stream_callback=None):
        stream_callback(draft)
        return draft

    agent.chat.side_effect = chat
    with patch("src.server._create_agent", return_value=agent), \
            patch("src.server.load_user_profile", return_value=UserProfile(user_id="facts-game-user")), \
            patch("src.server.log_event"):
        resp = TestClient(app_()).post("/api/coach/chat", headers={"X-User-Id": "facts-game-user"},
                                       json={"message": "Что мне теперь делать?", "session_id": session.id,
                                             "fen": _st2_fen()})
    text = "".join(json.loads(ln[6:]).get("delta", "") for ln in resp.text.splitlines() if ln.startswith("data: "))
    assert "увести ферзя" not in text and "Это главное сейчас." in text


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


# ── review of 30.10: what the first version cut wrongly or let through ────────────────────────────────────────

# A loaded game the student steps through: the board is after 6.O-O (ply 11), the PGN is the whole game.
REVIEW_PGN = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 5. d4 exd4 6. O-O Nxe4 7. cxd4 d5 8. dxc5 dxc4 9. Qxd8+ Kxd8"
# The prod 'attacked' board with h7-h6 in: the knight g5 hangs too (h6 and Qd8 hit it).
G5_HANGS = "r1bqkb1r/ppp2pp1/7p/n3p1N1/2B5/8/PPPP1PPP/RNBQK2R w KQkq - 0 7"
# White's b4 pawn hangs to Bf8 besides the bishop c4; Black's e5 and a5 hang as well.
B4_HANGS = "r1bqkb1r/ppp2ppp/5n2/n3p3/1PB5/5N2/P1PP1PPP/RNBQK2R w KQkq - 0 6"


def _moves_game(moves, student, question=""):
    board = chess.Board()
    for san in moves:
        board.push_san(san)
    ctx = CheckContext.from_fens([board.fen()], [], question=question, student_color=student)
    ctx.game_moves = list(moves)
    first = 0 if student == chess.WHITE else 1
    ctx.game_engine_moves = [m for i, m in enumerate(moves) if i % 2 != first]
    return ctx


def _review_at(ply, question="Разбери эту позицию"):
    board = chess.Board()
    for san in [x for x in REVIEW_PGN.replace(".", " ").split() if not x.isdigit()][:ply]:
        board.push_san(san)
    return CheckContext.from_fens([board.fen()], [REVIEW_PGN], question=question, student_color=chess.WHITE)


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "В этой позиции чёрные сыграли 6...Nxe4 — это и была ошибка.",
    "В этой позиции чёрные сыграли Nxe4 — забрали пешку.",
    "В этой партии ты потом сыграл 7.cxd4, и чёрные ответили 7...d5.",
    "В этой партии после размена ферзей на d8 чёрный король остался в центре.",
])
def test_moves_later_in_the_loaded_game_were_played_in_it(sentence):
    assert not [i for i in check_sentence(sentence, _review_at(11)) if "played" in i or "no capture" in i], sentence


@pytest.mark.unit
def test_a_wrong_move_later_in_the_loaded_game_is_read_against_the_game():
    issues = check_sentence("В этой партии ты сыграл 7.Re1.", _review_at(11))
    assert any("White played cxd4 here, not Re1" in i and "the game: 1.e4" in i and "9.Qxd8+ Kxd8" in i
               for i in issues), issues
    issues = check_sentence("В этой партии после размена на f7 чёрный король остался в центре.", _review_at(11))
    assert any("no capture was made on f7 in this game" in i and "9.Qxd8+ 9...Kxd8 (on d8)" in i for i in issues), issues


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Твой слон c4 под ударом только у коня a5.",                       # attacked only BY the knight
    "Твой слон на c4 атакован сейчас только конём, поэтому его легко увести.",
    "Конь g5 под ударом только ферзя d8 и защищён ферзём d1.",
    "The bishop on c4 is attacked only by the knight on a5.",
    "Только что твой слон оказался под ударом.",                       # «только что» = just now
    "Лишь только конь прыгнул на a5, слон c4 оказался под ударом.",
])
def test_only_about_the_attackers_or_just_now_is_not_an_exhaustive_claim(sentence):
    ctx = _moves_game("e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Na5".split(), chess.WHITE, "как дела?")
    assert not [i for i in check_sentence(sentence, ctx) if "under attack on the board" in i], sentence


@pytest.mark.unit
def test_a_pawn_is_not_a_figura():
    ctx = _moves_game("e4 e5 Nf3 Nf6".split(), chess.WHITE, "Что у меня под ударом?")
    for sentence in ("Ни одна фигура у тебя сейчас не под ударом.", "Ни одной фигуры у тебя не под ударом."):
        assert not [i for i in check_sentence(sentence, ctx) if "under attack on the board" in i], sentence
    issues = check_sentence("У тебя сейчас ничего не висит.",
                            _moves_game("e4 e5 Nf3 Nf6".split(), chess.WHITE, "Что у меня под ударом?"))
    assert any("the white pawn e4" in i for i in issues), issues


@pytest.mark.unit
@pytest.mark.parametrize("sentence,missed", [
    ("Под ударом у тебя только слон c4 — его атакуют чёрные.", "the white pawn d5"),      # the attackers' colour
    ("Под ударом у тебя только слон c4, на него напал конь чёрных.", "the white pawn d5"),
])
def test_the_attackers_colour_does_not_pick_the_side(sentence, missed):
    issues = check_sentence(sentence, CheckContext.from_fens([ATTACKED], question="Что у меня сейчас под ударом?",
                                                             student_color=chess.WHITE))
    assert any(missed in i and i.startswith("it is not the only one — White") for i in issues), issues


@pytest.mark.unit
def test_the_attackers_colour_does_not_pick_the_side_in_a_game():
    ctx = CheckContext.from_fens([B4_HANGS], question="Что у меня под ударом?", student_color=chess.WHITE)
    issues = check_sentence("Под ударом у тебя только слон c4 — его атакуют чёрные.", ctx)
    assert issues and all("White has more" in i and "the white pawn b4" in i for i in issues), issues


@pytest.mark.unit
def test_an_attacker_named_does_not_hide_a_hanging_piece_of_its_type():
    for sentence in ("Под ударом только слон c4: его атакует конь a5.",
                     "Под ударом только слон c4, который атакует чёрный конь."):
        issues = check_sentence(sentence, _study(G5_HANGS, "Что у меня сейчас под ударом?"))
        assert any("the white knight g5" in i for i in issues), (sentence, issues)
    ctx = _study(G5_HANGS, "Что у меня сейчас под ударом?")
    assert check_sentence("Под ударом у тебя слон c4 — его атакует конь a5.", ctx) == []
    assert any("the white knight g5" in i for i in check_sentence("Больше ничего не висит.", ctx))
    # the knight named as attacked does exclude it
    ctx = _study(G5_HANGS, "Что у меня сейчас под ударом?")
    assert check_sentence("Под ударом слон c4, конь g5 и пешка d5.", ctx) == []
    assert not [i for i in check_sentence("Больше ничего не висит.", ctx) if "under attack" in i]


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Белым стоит увести своего слона на h4, пока ты не сыграл h6.",     # «своего» = White's (the subject's)
    "Белые должны сейчас отвести своего слона на f4.",
])
def test_the_reflexive_possessive_follows_the_subject(sentence):
    ctx = _moves_game("d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 Nbd7".split(), chess.BLACK, "какой у белых план?")
    assert not [i for i in check_sentence(sentence, ctx) if "cannot go to" in i], sentence


@pytest.mark.unit
def test_the_reflexive_possessive_with_no_subject_is_the_students():
    issues = check_sentence("Тебе нужно увести своего ферзя на b6.", _game())
    assert any("black queen on d8 cannot go to b6" in i for i in issues), issues
    issues = check_sentence("Сейчас уведи своего ферзя на c7.", _game())
    assert any("black queen on d8 cannot go to c7" in i for i in issues), issues


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Белые с темпом атакуют ферзя, так что уведи ферзя на d6.",        # «белые» attack: not the queen's owner
    "Белые напали конём на ферзя, поэтому сейчас надо увести ферзя на a5.",
    "Конь белых бьёт по ферзю — уведи ферзя на a5.",
    "Коня с c6 стоит увести на d7 через b8 — это классический манёвр Брейера.",  # a route of several moves
])
def test_the_attacking_side_is_not_the_owner_and_a_route_is_a_plan(sentence):
    if "Брейера" in sentence:
        ctx = _moves_game("e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O h3".split(), chess.BLACK, "какой план?")
    else:
        ctx = _moves_game("e4 d5 exd5 Qxd5 Nc3".split(), chess.BLACK, "Что мне делать?")
    assert not [i for i in check_sentence(sentence, ctx) if "cannot go to" in i and "advise only" in i], sentence


@pytest.mark.unit
@pytest.mark.parametrize("sentence,wrong", [
    ("В этой партии ты сыграл 3.Кf3.", "White played Nc3 here, not Nf3"),
    ("Здесь ты пошёл 3.Кf3, а надо было d4.", "White played Nc3 here, not Nf3"),
    ("Здесь ты ответил 3...Фd6.", "Black played Qa5 here, not Qd6"),
    ("В этой партии соперник сыграл 3...Фd6.", "Black played Qa5 here, not Qd6"),
])
def test_you_played_is_read_by_the_numbering_outside_a_live_game(sentence, wrong):
    board = chess.Board()
    for san in "e4 d5 exd5 Qxd5 Nc3 Qa5 d4 Nf6".split():
        board.push_san(san)
    ctx = CheckContext.from_fens([board.fen()], ["1. e4 d5 2. exd5 Qxd5 3. Nc3 Qa5 4. d4 Nf6"], question="Разбери мою партию")
    assert any(wrong in i for i in check_sentence(sentence, ctx)), sentence
    ctx = CheckContext.from_fens([board.fen()], ["1. e4 d5 2. exd5 Qxd5 3. Nc3 Qa5 4. d4 Nf6"], question="Разбери мою партию")
    assert check_sentence("Здесь ты сыграл 3.Кc3, а соперник ответил 3...Фa5.", ctx) == []


@pytest.mark.unit
def test_you_played_is_not_read_against_the_book():
    # No record of the student's own game: the book's line through the board is not it (another order is possible).
    ctx = _study(NAJDORF, "Как называется этот дебют?")
    assert not [i for i in check_sentence("Здесь ты сыграл 2.Кc3.", ctx) if "played" in i]


@pytest.mark.unit
def test_the_book_index_is_never_built_on_the_event_loop(monkeypatch):
    import asyncio
    import threading

    import src.answer_check_facts as facts

    built = threading.Event()
    monkeypatch.setattr(facts, "_BOOK_THROUGH", None)
    monkeypatch.setattr(facts, "_build_book_index", lambda: built.set() or {})

    async def turn():
        return check_sentence(PROD_NAJDORF, _study(NAJDORF, "Какие главные теоретические продолжения за белых здесь?"))

    assert not [i for i in asyncio.run(turn()) if "has not been played" in i]  # not built yet: not judged
    assert built.wait(5)  # built in the background meanwhile


@pytest.mark.unit
def test_the_voice_check_reads_nothing_else_with_the_sentences_before_it():
    client = TestClient(app_())
    user = {"X-User-Id": "voice-facts-user"}
    body = {"text": "Больше ничего не висит.", "fen": ATTACKED, "question": "Что у меня сейчас под ударом?"}
    resp = client.post("/api/coach/voice/check", headers=user,
                       json={**body, "previous": "Под ударом у тебя слон на c4: его атакует конь a5."})
    assert resp.status_code == 200
    assert any("nothing else is in danger" in i and "the white pawn d5" in i for i in resp.json()["issues"])
    resp = client.post("/api/coach/voice/check", headers=user,
                       json={**body, "previous": "Под ударом у тебя слон на c4 и пешка d5."})
    assert resp.json()["issues"] == []
    assert client.post("/api/coach/voice/check", headers=user, json=body).json()["issues"] == []  # older sites
