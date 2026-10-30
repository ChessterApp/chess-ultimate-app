"""Prod re-check of Hermes 29.10 (29.10, live runs on chesster.io).

Voice: «Давай сыграем, я белыми» → «Нет, давай лучше заново, я чёрными». The model's start_game came with the
student's words in ``said`` and was refused («The student's words do not ask for a game.») while the site's restart
went through; the coach then said «партия уже началась, может продолжишь за белых?» over a new game as Black.
Words that ask for the game again are a request for a game."""

import json

import chess
import pytest

from src import game_mode
from src.sessions import session_store
from src.tools.game_play import _handle_game_action, _handle_start_game


@pytest.fixture(autouse=True)
def engine(monkeypatch):
    def move(fen, elo):
        board = chess.Board(fen)
        for san in ("e4", "e5", "Nf3", "Nc6"):
            try:
                return board.parse_san(san).uci()
            except ValueError:
                continue
        return next(iter(board.legal_moves)).uci()

    monkeypatch.setattr(game_mode, "_engine_move", move)
    monkeypatch.setattr(game_mode, "_evaluate", lambda fen, pov: (0, None))
    session_store._sessions.clear()
    yield
    session_store._sessions.clear()


AGAIN = "Нет, давай лучше заново. Я чёрными."


def _games(session):
    return [b for b in session.boards if b.kind == "game"]


def _playing(session):
    return [g for g in _games(session) if g.game_state["status"] == "playing"]


@pytest.mark.unit
def test_restart_words_with_no_game_at_all_are_still_refused():
    session = session_store.create("u")
    out = json.loads(_handle_start_game({"said": AGAIN}, session_id=session.id, user_id="u", utterance=AGAIN))
    assert "error" in out


@pytest.mark.unit
def test_words_that_ask_for_nothing_are_still_refused():
    session = session_store.create("u")
    out = json.loads(_handle_start_game({"said": "Какой был твой последний ход?"}, session_id=session.id, user_id="u"))
    assert "error" in out


# ── the answer check (prod text games, sets and Live runs 29.10) ─────────────────────────────────────────────

import chess.pgn  # noqa: E402

from src.answer_check import CheckContext, check_sentence, proposed_move  # noqa: E402


def _game_ctx(moves, student, question=""):
    board = chess.Board()
    for san in moves:
        board.push_san(san)
    ctx = CheckContext.from_fens([board.fen()], question=question)
    first = 0 if student == chess.BLACK else 1
    ctx.game_engine_moves = [m for i, m in enumerate(moves) if i % 2 == first]
    ctx.game_moves = list(moves)
    ctx.add_line(str(chess.pgn.Game.from_board(board)))
    ctx.student_color = student
    return ctx


@pytest.mark.unit
def test_my_last_move_is_the_games_last_move():
    ctx = _game_ctx(["e4", "e5", "Bc4", "Nc6", "d3"], chess.BLACK, "Что ты сейчас сыграл?")
    assert check_sentence("Мой последний ход — Bc4 от белых: слон с f1 встал на c4.", ctx)
    assert check_sentence("Мой последний ход был Bc4.", ctx)
    assert not check_sentence("Мой последний ход — d3: пешка с d2 на d3.", ctx)
    assert not check_sentence("Мой последний ход был 3.d3.", ctx)


@pytest.mark.unit
def test_a_move_told_from_square_to_square_then_what_it_attacks():
    ctx = _game_ctx(["d4", "Nf6"], chess.WHITE, "d4")
    assert check_sentence("d4 — и чёрные ответили Nf6: конь с g8 на f6 вышел в центр и сразу напал на твою пешку d4.", ctx)
    assert check_sentence("Мой последний ход — Nf6: конь с g8 встал на f6, вышел в центр и напал на твою пешку d4.", ctx)
    ok = _game_ctx(["e4", "Nf6"], chess.WHITE, "e4")
    assert not check_sentence("Чёрные ответили Nf6: конь с g8 на f6 вышел в центр и напал на твою пешку e4.", ok)


@pytest.mark.unit
def test_nothing_covers_it_is_undefended():
    ctx = _game_ctx(["d4", "Nf6"], chess.WHITE, "d4")
    assert check_sentence("Конь на f6 ничем не прикрыт, так что за пешку d4 можно не бояться.", ctx)


@pytest.mark.unit
def test_a_piece_said_to_support_a_pawn_it_does_not_reach():
    ctx = _game_ctx("e4 c5 Nf3 d6 Bc4 e6 O-O Nf6 d3 h6 h3 Nc6".split(), chess.WHITE, "h3")
    assert check_sentence("Чёрные ответили Nc6: конь с b8 встал на c6 и подкрепил пешку c5 в центре.", ctx)
    assert not check_sentence("Чёрные ответили d6: пешка с d7 на d6 подкрепила пешку c5.", ctx)


MOVES_V2 = ["d4", "e5", "Nc3", "Nc6", "dxe5", "Nf6", "exf6", "Be7", "fxe7"]


@pytest.mark.unit
def test_the_coachs_own_pawn_taking_is_not_advice_to_the_student():
    ctx = _game_ctx(MOVES_V2, chess.BLACK, "слон Е7")
    assert proposed_move("Слон на е7, и моя пешка на f6 забирает твоего слона.", ctx) is None


@pytest.mark.unit
def test_a_capture_the_engine_never_made():
    ctx = _game_ctx(MOVES_V2, chess.BLACK, "слон Е7")
    assert check_sentence("Моя пешка на e7 забрала ферзя, теперь твой ход.", ctx)
    assert not check_sentence("Моя пешка съела пешку на е5.", ctx)
    assert not check_sentence("Я забрал твоего слона на e7.", ctx)
    done = _game_ctx(MOVES_V2 + ["d6", "exd8=B"], chess.BLACK, "пешка d6")
    assert not check_sentence("Моя пешка на e7 забрала ферзя и превратилась в слона!", done)


@pytest.mark.unit
def test_an_opening_asked_about_is_not_the_game_on_the_board():
    ctx = _game_ctx(["d4", "d5", "c4", "dxc4"], chess.WHITE, "Какой основной ответ чёрных на ферзевый гамбит?")
    assert not check_sentence("Чаще всего чёрные играют е6, создавая крепкую защиту, это называется отказанный ферзевый гамбит.", ctx)
    assert not check_sentence("Или c6, это славянская защита.", ctx)
    named = _game_ctx(["d4", "d5", "c4", "dxc4"], chess.WHITE, "Как называется этот дебют?")
    assert check_sentence("Это отказанный ферзевый гамбит.", named)


# ── the review of this fix (29.10): true sentences the new rules must let through, false ones they must catch ──
W, B = chess.WHITE, chess.BLACK
REVIEW_CASES = [ # (moves, student, sentence, expect_flag)
 ("e4 e5 Nf3 Nf6 Nxe5 d6 Nf3 Nxe4 d3 Nf6",W,"На четвёртом ходу я взял конём пешку на e4.",False),
 ("e4 e5 Nf3 Nf6 Nxe5 d6 Nf3 Nxe4 d3 Nf6",W,"Я забрал конём твою пешку e4, а потом отступил на f6.",False),
 ("a4 h5 Ra3 Rh6 Rd3 Rd6 Rxd6 exd6",W,"Я взял пешкой ладью на d6 и раскрыл своего слона.",False),
 ("e4 e5 Nf3 Nc6 Bb5 a6 Bxc6 dxc6 d3 Bd6",W,"На четвёртом ходу я взял пешкой твоего слона на c6.",False),
 ("e4 e5 Nf3 d6 Bc4 Bg4 Nc3 g6 Nxe5",W,"Ты оставил ферзя под боем, чтобы я взял ферзя и попал под мат.",False),
 ("e4 e5 Nf3 d6 Bc4 Bg4 Nc3 g6 Nxe5",W,"Я взял ферзя? Нет, ферзь остался стоять, ведь после этого меня ждал мат.",False),
 ("e4 d5 exd5 Nf6",W,"Ты пишешь «я взял пешку» — верно, твоя пешка взяла пешку на d5.",False),
 ("e4 a6 e5 d5 exd6",B,"Я забрал твою пешку на d5 взятием на проходе.",False),
 ("e4 e5 Nf3 Nc6",W,"В прошлой партии я забрал твоего ферзя на d8, а в этой пока никто ничего не брал.",False),
 ("a4 h5 g4 hxg4 Nf3 g3 Nd4 gxh2 Rg1 hxg1=Q",W,"Мой ферзь забрал ладью на g1 — пешка дошла до конца и превратилась.",False),
 ("e4 d5 exd5 Qxd5",W,"Я забрал ферзём пешку на d5.",False),
 ("d4 e5 Nc3 Nc6 dxe5 Nf6 exf6 Be7 fxe7",B,"Моя пешка на e7 забрала ферзя, теперь твой ход.",True),
 ("e4 e5 Nf3 Nf6 Nxe5 d6 Nf3 Nxe4 d3 Nf6",W,"Я взял слоном пешку на e4.",True),
 ("e4 e5 Nf3 Nc6 Bc4 Bc5 O-O Nf6 g4 d6 h4 h6",W,"Твой король на g1 совсем не прикрыт пешками.",False),
 ("e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nf6",W,"Твой конь на d4 не прикрыт пешкой, его держит только ферзь d1.",False),
 ("e4 e5 Bc4 Nc6 Qh5",B,"Пешка на f7 не прикрыта ничем, кроме короля.",False),
 ("e4 e5 f4 exf4 Nf3 d6 Bc4 Be7",B,"Мой король на e1 не прикрыт от шаха на h4, поэтому я сыграл Nf3.",False),
 ("d4 Nf6",W,"Конь на f6 ничем не прикрыт, так что за пешку d4 можно не бояться.",True),
 ("d4 d5 c4 e6 Nc3 Nc6 Nf3 Nce7",W,"Мой конь на c6 отступил и прикрыл пешку d5.",False),
 ("d4 d5 Nc3 e6 e3 c5 Nce2",B,"Мой конь на c3 отступил и защитил d4.",False),
 ("d4 Nf6",W,"d4 — и чёрные ответили Nf6: конь с g8 на f6 вышел в центр и сразу напал на твою пешку d4.",True),
 ("e4 e5 Nf3 Nc6 Bb5 a6",W,"Мой последний ход был ответом на твоего слона b5 — a6.",False),
 ("e4 e5 Nf3 Nc6 Bb5 a6",W,"Мой последний ход — ответ на Bb5: я сыграл a6.",False),
 ("e4 e5 Bc4 Nc6 d3",B,"Мой последний ход — Bc4 от белых.",True),
]


@pytest.mark.unit
@pytest.mark.parametrize("moves,student,sentence,wrong", REVIEW_CASES)
def test_review_cases(moves, student, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(moves.split(), student))) == wrong


REVIEW_QUESTIONS = [("Мы сейчас играем ферзевый гамбит?","Да, это принятый ферзевый гамбит.",True),("Это ферзевый гамбит?","Да, это принятый ферзевый гамбит.",True),
         ("Какой основной ответ чёрных на ферзевый гамбит?","Чаще всего чёрные играют е6, это называется отказанный ферзевый гамбит.",False)]


@pytest.mark.unit
@pytest.mark.parametrize("question,sentence,wrong", REVIEW_QUESTIONS)
def test_review_opening_questions(question, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(["d4", "d5", "c4", "e6"], chess.WHITE, question))) == wrong


# ── second review round (29.10) ──────────────────────────────────────────────────────────────────────────────
ROUND2_CASES = [
 ("e4 e5 Nf3 Bc5 Nc3 Bf8 d4", W, "Мой слон вернулся на f8, а ты, не теряя времени, напал на e5.", False),
 ("e4 e5 Nf3 Bc5 Nc3 Bf8 d4", W, "Мой слон вернулся на f8, а ты тут же и напал на e5.", False),
 ("e4 Nf6 e5 Ng8 Bd3", W, "Мой конь отступил на g8, но белые, конечно, нацелились на h7.", False),
 ("e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nxd4 Qxd4", W, "В предыдущей партии я забрал твоего ферзя, а сейчас пока только размены.", False),
 ("e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nxd4 Qxd4", W, "В той партии я забрал ладью на a1.", False),
 ("e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nxd4 Qxd4", W, "До отката я забрал твоего ферзя, но ты вернул ход.", False),
 ("e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nxd4 Qxd4", W, "Раньше я уже забрал ладью в похожей позиции.", False),
 ("e4 d5 exd5 Qxd5 Nc3 Qa5 d4 Nf6 Nf3 Bg4 h3 Bxf3 Qxf3", W, "Ты сказал, что я взял твоего ферзя, но ферзь на месте.", False),
 ("e4 d5 exd5 Qxd5 Nc3 Qa5 d4 Nf6 Nf3 Bg4 h3 Bxf3 Qxf3", W, "Кажется, ты считаешь, что я забрал твоего слона, а я забрал коня.", False),
 ("e4 e5 Nf3 Nc6 Bb5 a6", W, "Мой последний ход был не Nf6, а a6.", False),
 ("e4 e5 Nf3 Nc6 Bb5 a6", W, "Нет, мой последний ход — не Nf6, а a6.", False),
 ("e4 e5 Bc4 Nc6 Qh5", B, "Пешка на f7 ничем не прикрыта, если не считать короля.", False),
 ("e4 e5 Bc4 Nc6 Qh5", B, "Пешка на f7 никем не прикрыта, только королём.", False),
 ("d4 Nf6", W, "Чёрные ответили Nf6: конь с g8 на f6 вышел в центр и сразу напал на твою пешку d4.", True),
 ("d4 Nf6", W, "Мой последний ход — Nf6: конь с g8 встал на f6, вышел в центр и напал на твою пешку d4.", True),
]
ROUND2_QUESTIONS = [
 ("Я разыграл ферзевый гамбит?", "Да, ты разыграл принятый ферзевый гамбит.", True),
 ("Ферзевый гамбит принятый или отказанный? Что у нас получилось?", "У тебя получился принятый ферзевый гамбит.", True),
 ("Какой основной ответ чёрных на ферзевый гамбит?", "Чаще всего чёрные играют е6, это называется отказанный ферзевый гамбит.", False),
]


@pytest.mark.unit
@pytest.mark.parametrize("moves,student,sentence,wrong", ROUND2_CASES)
def test_round2_cases(moves, student, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(moves.split(), student))) == wrong


@pytest.mark.unit
@pytest.mark.parametrize("question,sentence,wrong", ROUND2_QUESTIONS)
def test_round2_opening_questions(question, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(["d4", "d5", "c4", "e6"], chess.WHITE, question))) == wrong


# ── third review round (29.10) ───────────────────────────────────────────────────────────────────────────────
ROUND3_CASES = [
 ("e4 e5 Nf3 Nc6 d4 d6 Nc3 Nf6 Bb5 Bg4", W, "Мой слон на g4 взял твоего коня в связку.", False),
 ("e4 e5 Nf3 Nc6 d4 d6", W, "Я взял пешку e5 под защиту ходом d6.", False),
 ("e4 e5 Nf3 Nc6 d4 d6", W, "Мой конь взял пешку d4 на прицел.", False),
 ("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6", W, "Мой конь взял пешку e4 в оборот.", False),
 ("e4 e5 Nf3 Nf6", W, "Мой последний ход — конь с g8 на f6.", False),
 ("e4 e5 Nf3 Nf6", W, "My last move was the knight from g8 to f6.", False),
 ("e4 e5 Nf3 d6", W, "Мой последний ход — пешка с d7 на d6.", False),
 ("e4 e5 Nf3 d6", W, "Мой последний ход — защита пешки e5.", False),
 ("e4 e5 Nf3 d6", W, "Мой последний ход — вместо Nc6 я сыграл d6.", False),
 ("e4 e5 Nf3 d6", W, "Мой последний ход — Nc6.", True),
 ("e4 e5 Nf3 d6", W, "My last move was Nc6.", True),
 ("e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nf6 Nc3 Bb4", W, "Конь на c3 ничем не прикрыт со стороны слона b4: он связан.", False),
 ("e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nf6 Nc3 Bb4", W, "Конь на d4 ничем не прикрыт с фланга.", False),
 ("e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nf6 Nc3 Bb4", W, "Конь на c3 ничем не прикрыт — разве что пешкой b2.", False),
 ("e4 e5 Nf3 Nc6 Bc4 Nf6 d3 Bc5", B, "Конь встал на c6, вышел вперёд слон и напал на f2.", False),
 ("e4 e5 Nf3 Nc6 Bc4 Nf6 d3 Bc5", B, "Мой конь встал на f6, вышел мой слон и напал на f2.", False),
 ("d4 d5 Nc3 Nf6 Bf4 e6 Qd2 Be7 Rd1 O-O", B, "Ладья встала на d1 за ферзём и поддержала пешку d4.", False),
]


@pytest.mark.unit
@pytest.mark.parametrize("moves,student,sentence,wrong", ROUND3_CASES)
def test_round3_cases(moves, student, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(moves.split(), student))) == wrong


# ── fourth review round (29.10) ──────────────────────────────────────────────────────────────────────────────
ROUND4_CASES = [
 ("e4 e5 Nf3 Nc6 Ng5 d6 Nf3", B, "Мой конь прыгнул на g5, вернулся на f3 и держит e5.", False),
 ("e4 e5 Qh5 Nc6 Bc4 Nf6 Qe2 d6", B, "Ферзь вышел на h5, вернулся на e2 и защитил пешку e4.", False),
 ("e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5", B, "Мой конь с f3 прыгнул на g5 и поддержал слона c4 в атаке на f7.", False),
 ("e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5 Qf3", B, "Ферзь встал на f3 и поддержал коня g5 в атаке на f7.", False),
 ("e4 e5 Nf3 Nc6", W, "Я забрал твоего коня на f3, но ты взял ход назад, и конь вернулся.", False),
 ("e4 e5 Nf3 Nc6", W, "Представь, что я взял пешку на e4: тогда твой конь сразу отыграет её.", False),
 ("e4 e5 Nf3 Nc6", W, "До отката мой последний ход был Nf6, а теперь я сыграл Nc6.", False),
 ("d4 Nf6 c4 c5", W, "Я взял пешку d4 под давление ходом c5.", False),
 ("e4 Nf6 Nc3 d5", W, "Я взял пешку e4 на мушку.", False),
 ("e4 e5 Nf3 Nc6", W, "По-твоему, я взял ферзя, но ферзь стоит на d1.", False),
]


@pytest.mark.unit
@pytest.mark.parametrize("moves,student,sentence,wrong", ROUND4_CASES)
def test_round4_cases(moves, student, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(moves.split(), student))) == wrong


# ── fifth review round (29.10) ───────────────────────────────────────────────────────────────────────────────
ROUND5_CASES = [
 ("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6 Be3 Bg7", W, "Мой слон с f8 на g7 ушёл и смотрит на твоего коня d4.", False),
 ("e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O h3 Bb7", W, "Мой слон с c8 на b7 вышел и давит на e4.", False),
 ("e4 e5 Nf3 d6 d4 exd4 Qxd4 Nc6 Qe3 Nf6 Nc3 Be7 Bd2 O-O O-O-O Re8", W,
  "Твой ферзь на e3 ничем не прикрыт: моя ладья e8 смотрит прямо на него, а дальше король.", True),  # integration 30.10: f2 and Bd2 defend it, White's e4 pawn stands between
 ("e4 e5 Nf3 Nc6", W, "В другой игре я забрал твоего ферзя.", False),
 ("e4 e5 Nf3 Nc6", W, "Тогда мой последний ход был Nf6, а теперь Nc6.", False),
]
OPENING_CASES = [  # (moves, question, sentence, wrong)
 ("d4 d5 c4 dxc4", "Какой основной ответ чёрных на ферзевый гамбит?",
  "Чаще всего чёрные играют е6, создавая крепкую защиту, это называется отказанный ферзевый гамбит.", False),
 ("d4 d5 c4 dxc4", "Какой основной ответ чёрных на ферзевый гамбит?", "Или c6, это славянская защита.", False),
 ("d4 d5 c4 e6 Nc3 Nf6", "Ферзевый гамбит принятый или отказанный?", "Это принятый ферзевый гамбит.", True),
 ("e4 c6 d4 d5 e5", "Какой вариант Каро-Канн я выбрал?", "Это атака Панова.", True),
 ("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6", "Какой вариант сицилианской защиты сыграли чёрные?", "Это вариант Найдорфа.", True),
 ("d4 d5 c4 e6 Nc3 Nf6", "Как дальше играть в ферзевом гамбите?", "Сейчас у нас принятый ферзевый гамбит: чёрные взяли пешку c4.", True),
]


@pytest.mark.unit
@pytest.mark.parametrize("moves,student,sentence,wrong", ROUND5_CASES)
def test_round5_cases(moves, student, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(moves.split(), student))) == wrong


@pytest.mark.unit
@pytest.mark.parametrize("moves,question,sentence,wrong", OPENING_CASES)
def test_opening_named_in_a_game(moves, question, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(moves.split(), chess.WHITE, question))) == wrong


# ── sixth review round (29.10) ───────────────────────────────────────────────────────────────────────────────
ROUND6_OPENINGS = [
 ("d4 d5 c4 dxc4", "Как называется этот дебют?", "У нас отказанный ферзевый гамбит: чёрные сыграли e6.", True),
 ("d4 d5 c4 e6 Nc3 Nf6", "Как называется этот дебют?", "Это принятый ферзевый гамбит: чёрные взяли dxc4.", True),
 ("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6", "Какой вариант сицилианской защиты сыграли чёрные?", "Это вариант Найдорфа: чёрные сыграли a6.", True),
 ("e4 e5 Nf3 Nc6 Bc4 Bc5", "Как называется этот дебют?", "Это защита двух коней: чёрные сыграли Nf6.", True),
]
ROUND6_CASES = [
 ("e4 e5", W, "Мой последний ход — e7–e5, симметричный ответ.", False),
 ("e4 e5", W, "My last move was e7–e5.", False),
 ("e4 d5 exd5 Qxd5", W, "Мой последний ход — Фd8–d5, ферзь забрал пешку.", False),
 ("e4 e5", W, "Мой последний ход — d7–d5.", True),
 ("e4 e5 Nf3 Nc6 Bc4 Nd4 c3 Nxf3+ Qxf3 Nf6 d3 Bc5 Bg5 h6", W, "Мой конь взял ферзя и ладью в вилку, но ты отказался от размена.", False),
]


@pytest.mark.unit
@pytest.mark.parametrize("moves,question,sentence,wrong", ROUND6_OPENINGS)
def test_round6_openings(moves, question, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(moves.split(), chess.WHITE, question))) == wrong


@pytest.mark.unit
@pytest.mark.parametrize("moves,student,sentence,wrong", ROUND6_CASES)
def test_round6_cases(moves, student, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(moves.split(), student))) == wrong


# ── seventh review round (29.10) ─────────────────────────────────────────────────────────────────────────────
ROUND7_OPENINGS = [
 ("d4 d5 c4 dxc4", "Как называется этот дебют?", "Это отказанный ферзевый гамбит: чёрные обычно играют здесь e6.", True),
 ("d4 d5 c4 dxc4", "Что это за дебют?", "Перед нами славянская защита: чёрные обычно отвечают c6.", True),
 ("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6", "Какой это вариант?", "Это вариант Найдорфа, типичный ход a6.", True),
]
ROUND7_CASES = [
 ("e4 e5 Qh5 Nc6 Bc4 Nf6 Qe2 d6", B, "Ферзь вышел на h5, вернулся назад и защитил пешку e4.", False),
 ("e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5", W, "Ты спросил, почему я забрал коня, но коня я не трогал — я взял пешку на d5.", False),
 ("e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5", W, "Ты утверждаешь, что я забрал слона, но я взял только пешку d5.", False),
 ("e4 e5 d4 exd4", W, "Мой последний ход — e5:d4.", False),
]


@pytest.mark.unit
@pytest.mark.parametrize("moves,question,sentence,wrong", ROUND7_OPENINGS)
def test_round7_openings(moves, question, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(moves.split(), chess.WHITE, question))) == wrong


@pytest.mark.unit
@pytest.mark.parametrize("moves,student,sentence,wrong", ROUND7_CASES)
def test_round7_cases(moves, student, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(moves.split(), student))) == wrong




# ── eighth review round (29.10) ──────────────────────────────────────────────────────────────────────────────
ROUND8_CASES = [
 ("e4 e5 Nf3 d6", W, "Мой ответ — d6: e5 теперь под защитой.", False),
 ("e4 e5 Nf3 Nf6", W, "Мой последний ход — Nf6: e4 под ударом.", False),
 ("e4 e5 Nf3 Nf6 Nxe5 d6 Nf3 Nxe4 Qe2 Qe7 d3 Nf6", W, "Ты подумал, что я забрал коня, но я взял пешку на e4.", False),
 ("e4 e5 Nf3 Nf6 Nxe5 d6 Nf3 Nxe4 Qe2 Qe7 d3 Nf6", W, "Неверно, что я забрал коня — я взял пешку на e4.", False),
 ("e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5", W, "Ты написал, что я забрал твоего коня, но на самом деле я взял пешку на d5.", False),
]
ROUND8_OPENINGS = [
 ("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6", "", "Получился вариант Найдорфа, обычно здесь играют a6.", True),
 ("d4 d5 c4 dxc4", "Как играть дальше?", "У тебя получился отказанный ферзевый гамбит, обычно чёрные играют e6.", True),
]


@pytest.mark.unit
@pytest.mark.parametrize("moves,student,sentence,wrong", ROUND8_CASES)
def test_round8_cases(moves, student, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(moves.split(), student))) == wrong


@pytest.mark.unit
@pytest.mark.parametrize("moves,question,sentence,wrong", ROUND8_OPENINGS)
def test_round8_openings(moves, question, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(moves.split(), chess.WHITE, question))) == wrong


# ── ninth review round (29.10) ───────────────────────────────────────────────────────────────────────────────
ROUND9_CASES = [
 ("e4 e5 Nf3 Nf6", W, "Мой ответ — Nf6 — e4 под ударом.", False),
 ("e4 e5 Nf3 Nc6 Bc4 Bc5", W, "Мой ответ — Bc5 — f2 на прицеле.", False),
 ("e4 e5 Nf3 Nc6", W, "Я забрал твоего коня, но ты взял ход обратно.", False),
 ("e4 e5 Nf3 Nc6", W, "Я забрал твоего коня, но ход отменён.", False),
 ("e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d4 exd4 cxd4 Bb4+", W, "Мой слон взял коня c3 на рентген.", False),
]
ROUND9_OPENINGS = [
 ("e4 c6 d4 d5 e5", "Как дальше?", "Сейчас разыгрывается атака Панова: обычно белые дальше играют c4.", True),
 ("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6", "", "Этот вариант называют Найдорфом, обычно чёрные играют a6.", True),
 ("d4 d5 c4 e6 Nc3 Nf6", "", "Такой дебют называется принятый ферзевый гамбит: чёрные обычно берут dxc4.", True),
]


@pytest.mark.unit
@pytest.mark.parametrize("moves,student,sentence,wrong", ROUND9_CASES)
def test_round9_cases(moves, student, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(moves.split(), student))) == wrong


@pytest.mark.unit
@pytest.mark.parametrize("moves,question,sentence,wrong", ROUND9_OPENINGS)
def test_round9_openings(moves, question, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(moves.split(), chess.WHITE, question))) == wrong


@pytest.mark.unit
@pytest.mark.parametrize("words", ["сыграем по новой", "давай заново"])
def test_the_sites_fallback_start_with_restart_words_after_a_finished_game_starts_it(words):
    session = session_store.create("u")
    _handle_start_game({"color": "white"}, session_id=session.id, user_id="u", utterance="Давай сыграем")
    _handle_game_action({"said": "сдаюсь"}, session_id=session.id, user_id="u", utterance="сдаюсь")
    out = json.loads(_handle_start_game({"said": words}, session_id=session.id, user_id="u", utterance=words, caller="site"))
    assert out.get("ok") and len(_playing(session)) == 1


# ── tenth review round (29.10) ───────────────────────────────────────────────────────────────────────────────
ROUND10_CASES = [
 ("d4 Nf6", W, "Чёрные ответили Nf6: конь с g8 встал на f6 и давит на d4 в борьбе за центр.", True),
 ("e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5", W, "Ты говорил, что я забрал твоего коня, но я взял только пешку d5.", False),
 ("e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5", W, "По твоим словам, я взял коня, но на самом деле я взял пешку на d5.", False),
]
ROUND10_OPENINGS = [
 ("e4 e5 Nf3 Nc6 Bc4 Bc5", "", "Чёрные чаще всего отвечают Nf6, и сейчас это защита двух коней.", True),
 ("e4 e5 Nf3 Nc6 Bb5", "Что дальше?", "Обычно играют Bc4, и твоя позиция — это итальянская партия.", True),
]


@pytest.mark.unit
@pytest.mark.parametrize("moves,student,sentence,wrong", ROUND10_CASES)
def test_round10_cases(moves, student, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(moves.split(), student))) == wrong


@pytest.mark.unit
@pytest.mark.parametrize("moves,question,sentence,wrong", ROUND10_OPENINGS)
def test_round10_openings(moves, question, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(moves.split(), chess.WHITE, question))) == wrong


@pytest.mark.unit
def test_the_fallback_restart_tells_the_new_games_colour():
    session = session_store.create("u")
    _handle_start_game({"color": "black"}, session_id=session.id, user_id="u", utterance="Давай сыграем, я чёрными")
    _handle_game_action({"said": "сдаюсь"}, session_id=session.id, user_id="u", utterance="сдаюсь")
    out = json.loads(_handle_start_game({"said": "сыграем по новой"}, session_id=session.id, user_id="u",
                                        utterance="сыграем по новой", caller="site"))
    assert out.get("ok") and out["student_color"] == "black" and out["engine_first_move"] == "e4"



# ── the restart words, site and model (29.10, final design) ────────────────────────────────────────────────────
@pytest.mark.unit
@pytest.mark.parametrize("model_first", [True, False])
def test_restart_words_are_one_restart_by_the_site_the_model_is_told_to_wait(model_first):
    session = session_store.create("u")
    _handle_start_game({"color": "white"}, session_id=session.id, user_id="u", utterance="Давай сыграем, я белыми.")
    game_mode.play_move(session, _games(session)[-1], "d4")
    model = lambda: json.loads(_handle_start_game({"color": "black", "said": AGAIN}, session_id=session.id, user_id="u",
                                                  utterance=AGAIN))
    site = lambda: json.loads(_handle_game_action({"said": AGAIN}, session_id=session.id, user_id="u", utterance=AGAIN))
    model_out, site_out = (model(), site()) if model_first else (site(), model())[::-1]
    assert "error" in model_out and "NEW game" in model_out["error"] and "game_action" in model_out["error"]
    assert site_out.get("ok")
    playing = _playing(session)
    assert len(_games(session)) == 2 and len(playing) == 1
    assert playing[0].game_state["student_color"] == "black" and playing[0].game_state["moves"] == ["e4"]


# ── eleventh review round (29.10) ────────────────────────────────────────────────────────────────────────────
ROUND11_OPENINGS = [
 ("d4 d5 c4 dxc4", "Что дальше?", "Чёрные защитили центр ходом e6 — это отказанный ферзевый гамбит, главная линия.", True),
 ("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6", "", "Пятым ходом чёрные двинули a6, обычно это вариант Найдорфа.", True),
]
ROUND11_CASES = [
 ("e4 e5 Nf3 Nc6 Bc4 Bd6", W, "Мой слон вышел на d6 и смотрит на h2.", True),
 ("e4 e5 Nf3 Nc6", W, "В той игре я взял твоего ферзя.", False),
 ("e4 e5 Nf3 Nc6", W, "До рестарта я забрал твоего ферзя.", False),
 ("e4 e5 Nf3 Nc6 Bc4 Nf6 d3 Be7", W, "Я взял пешку e5 под охрану.", False),
]


@pytest.mark.unit
@pytest.mark.parametrize("moves,question,sentence,wrong", ROUND11_OPENINGS)
def test_round11_openings(moves, question, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(moves.split(), chess.WHITE, question))) == wrong


@pytest.mark.unit
@pytest.mark.parametrize("moves,student,sentence,wrong", ROUND11_CASES)
def test_round11_cases(moves, student, sentence, wrong):
    assert bool(check_sentence(sentence, _game_ctx(moves.split(), student))) == wrong



@pytest.mark.unit
def test_the_models_call_with_only_the_words_does_not_restart():
    session = session_store.create("u")
    _handle_start_game({"color": "white"}, session_id=session.id, user_id="u", utterance="Давай сыграем")
    game_mode.play_move(session, _games(session)[-1], "d4")
    words = "Давай заново, посложнее"
    site = json.loads(_handle_game_action({"said": words}, session_id=session.id, user_id="u", utterance=words))
    model = json.loads(_handle_start_game({"said": words}, session_id=session.id, user_id="u", utterance=words))
    assert site.get("ok") and "error" in model
    assert len(_games(session)) == 2 and len(_playing(session)) == 1


@pytest.mark.unit
def test_the_site_marker_reaches_the_tool_through_the_bridge():
    from src.tool_bridge import _dispatch_voice

    session = session_store.create("u")
    _handle_start_game({"color": "black"}, session_id=session.id, user_id="u", utterance="Давай сыграем, я чёрными")
    _handle_game_action({"said": "сдаюсь"}, session_id=session.id, user_id="u", utterance="сдаюсь")
    model = json.loads(_dispatch_voice("start_game", {"said": "сыграем по новой"}, session, "сыграем по новой"))
    assert "error" in json.dumps(model) and not _playing(session)
    site = json.loads(_dispatch_voice("start_game", {"said": "сыграем по новой"}, session, "сыграем по новой", "site"))
    assert "error" not in json.dumps(site)[:40] and len(_playing(session)) == 1



@pytest.mark.unit
def test_with_no_site_call_the_models_game_action_restart_does_it_once():
    session = session_store.create("u")
    _handle_start_game({"color": "white"}, session_id=session.id, user_id="u", utterance="Давай сыграем")
    game_mode.play_move(session, _games(session)[-1], "d4")
    words = "Давай по новой, я чёрными"
    told = json.loads(_handle_start_game({"said": words}, session_id=session.id, user_id="u", utterance=words))
    assert "game_action" in told["error"]
    done = json.loads(_handle_game_action({"action": "restart"}, session_id=session.id, user_id="u", student_message=words))
    assert done.get("ok") and _playing(session)[0].game_state["student_color"] == "black"
    again = json.loads(_handle_game_action({"said": words}, session_id=session.id, user_id="u", utterance=words))
    assert again.get("ok") and len(_games(session)) == 2, "the site's call for the same words a moment later is the same restart"
