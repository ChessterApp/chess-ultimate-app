"""F6 of the 01.11 fixes: endgames, engine claims and trades read by their parts (reviews review-fp / review-miss).

  race_distance — the king is found by its square («король на h1»), a genitive («король чёрных») or «их», so the
                  pawn's own king is not read as the chaser; a support verb («поддержать», «помочь») is not the race;
                  a noun after a preposition («далеко от пешки … не успеет») is not the subject; the same verdict in
                  other words (a tempo short, falling behind, not reaching the pawn, the square entered or not).
  mate_squares  — a modal («можно», «могут») is either reading, judged when both are false; in an ending where mate
                  is never forced every reading is the possibility one; «без угла … не», «… — иначе мата нет», «на
                  краю мата не бывает», «только там», «только угловое поле», squares named.
  piece_decides — the outcome predicate and its one actor in any case and order («ход ферзя», «ферзём ты
                  выигрываешь», «решающий удар наносит ферзь»); any word the claim does not explain leaves it unjudged.
  trades        — an exchange inside a longer run of captures is a window of its own when it is settled on its
                  square; checks and their replies do not break a combination; nouns, passives and receiving verbs.
"""
from __future__ import annotations

import chess
import pytest

from src.answer_check import CheckContext, check_sentence
from src.endgame_claims import outcome_issues
from src.famous_games import GAMES, _pgn
from src.line_verdict import _outcome_parts, _piece_claims
from src.trade_claims import frames, trade_issues

SQUARE = "8/8/8/P3k3/8/8/8/7K b - - 0 1"  # tablebase: draw (1...Kd5, 1...Kd6)
FAR_LOST = "8/8/8/P7/7K/8/8/6k1 b - - 0 1"  # Kg1 outside the square: White wins
F2_LOST = "8/8/1k6/8/8/8/5PK1/8 w - - 0 1"  # White wins (f4)
RACE_Q = "Я чёрными, мой ход. Догонит ли мой король пешку?"
KNNK = "8/8/8/8/8/2k5/8/K1N1N3 w - - 0 1"
KRK = "8/8/8/4k3/8/8/8/R3K3 w - - 0 1"
KQK = "k7/8/1Q6/8/8/8/8/2K5 b - - 0 1"
KBNK = "8/8/8/4k3/8/8/8/2BNK3 w - - 0 1"
SCHOLAR = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"


@pytest.fixture(autouse=True)
def _switches(monkeypatch):
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW", raising=False)


def _race(fen: str, tablebase: str, question: str = RACE_Q) -> CheckContext:
    ctx = CheckContext.from_fens([fen], [], question=question)
    ctx.language = "ru"
    ctx.tablebase = tablebase
    ctx.engine_eval = 0.0 if tablebase == "draw" else (20.0 if tablebase.startswith("White") else -20.0)
    return ctx


def _plain(fen: str) -> CheckContext:
    ctx = CheckContext.from_fens([fen], [])
    ctx.language = "ru"
    return ctx


def _race_issues(sentence: str, ctx) -> list:
    return outcome_issues(sentence.lower().replace("ё", "е"), ctx)


# ── race_distance ────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("fen,tb,sentence", [
    # the pawn's own king, named by its square, without «на», or by «их» (review-fp R5)
    (SQUARE, "draw", "Король на h1 слишком далеко от пешки a5 и не сможет её поддержать."),
    (SQUARE, "draw", "Король h1 слишком далеко, пешке он не поможет."),
    (SQUARE, "draw", "Их король слишком далеко, чтобы поддержать пешку."),
    (SQUARE, "draw", "Король на h1 не дотянется до пешки, чтобы её поддержать."),
    (SQUARE, "draw", "Король соперника слишком далеко от пешки."),
    (SQUARE, "draw", "Белому королю не хватает времени, чтобы помочь пешке."),
    # a noun after a preposition is not who «успевает» (review-fp race-01, race-13: cut on main too)
    (SQUARE, "draw", "Король чёрных не слишком далеко от пешки и успевает её догнать."),
    (F2_LOST, "White wins", "Король b6 далеко от пешки f2 и не успеет её остановить."),
    # the new predicates, said truly
    (SQUARE, "draw", "Король на e5 входит в квадрат пешки."),
    (SQUARE, "draw", "Король чёрных не отстаёт: он успевает к пешке."),
    (FAR_LOST, "White wins", "Королю g1 не хватает темпа."),
    (FAR_LOST, "White wins", "Чёрный король не попадает в квадрат, пешка проходит."),
    (FAR_LOST, "White wins", "Чёрный король отстаёт, и пешка становится ферзём."),
    # escorting is not the race: left unjudged
    (SQUARE, "draw", "Белый король успевает поддержать пешку."),
    (SQUARE, "draw", "Пешка слишком далеко."),
])
def test_true_race_sentences_pass(fen, tb, sentence):
    assert _race_issues(sentence, _race(fen, tb)) == []


@pytest.mark.parametrize("fen,tb,sentence", [
    (SQUARE, "draw", "Пешка a5 убегает: твоему королю не хватает одного темпа."),
    (SQUARE, "draw", "Королю на e5 до пешки не дойти."),
    (SQUARE, "draw", "Чёрный король отстаёт, и пешка становится ферзём."),
    (SQUARE, "draw", "Король чёрных не попадает в квадрат пешки."),
    (SQUARE, "draw", "Чёрный король не входит в квадрат пешки."),
    (SQUARE, "draw", "Твоему королю до пешки уже не добраться."),
    (SQUARE, "draw", "Король на e5 слишком далеко от пешки a5."),  # the chaser named by its square
    (FAR_LOST, "White wins", "Король g1 попадает в квадрат пешки."),
    (FAR_LOST, "White wins", "Чёрный король успевает войти в квадрат."),
])
def test_wrong_race_sentences_are_cut(fen, tb, sentence):
    issues = _race_issues(sentence, _race(fen, tb))
    assert issues and "tablebase" in issues[0], issues


def test_a_king_named_where_no_king_stands_is_another_position():
    assert _race_issues("Король на e4 слишком далеко от пешки.", _race(SQUARE, "draw")) == []


# ── mate_squares ─────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("fen,sentence", [
    (KNNK, "Мат двумя конями можно поставить только в углу."),
    (KNNK, "Два коня могут дать мат только в углу."),
    (KNNK, "Мат двумя конями ставится лишь в углу доски."),  # never forced: the possibility reading
    (KNNK, "На краю доски два коня мат не дают, только в углу."),
    (KNNK, "Мата двумя конями на краю не бывает."),
    (KNNK, "Без угла два коня заматовать не могут."),
    (KNNK, "Король должен оказаться в углу — иначе мата двумя конями нет."),
    (KNNK, "Нужно, чтобы король сам пришёл в угол — только там он получает мат."),
    (KNNK, "Только угловое поле подходит для мата двумя конями."),
    (KNNK, "Мат получится, только если король встанет на a8, h8, a1 или h1."),
    (KNNK, "Матовая позиция с двумя конями существует только в углу."),
    (KRK, "Ладьёй можно заматовать только в углу."),  # modal: false as possible and as forced
    (KQK, "На краю мата ферзём не бывает."),
])
def test_wrong_mate_places_are_cut(fen, sentence):
    issues = check_sentence(sentence, _plain(fen))
    assert issues and "edge" in issues[0], issues


@pytest.mark.parametrize("fen,sentence", [
    (KRK, "Ладьёй можно заматовать только на краю."),
    (KBNK, "Слоном и конём мат можно поставить только в углу."),  # forced reading not solved for KBNK
    (KBNK, "Слоном и конём мат можно форсировать только в углу."),
    (KNNK, "Двумя конями мат можно поставить и на краю, не только в углу."),
    (KNNK, "На краю мат не ставится."),  # the forced mate: never forced in KNNK, true
    (KNNK, "На краю двумя конями мат не поставить."),
    (KNNK, "Форсировать мат двумя конями нельзя: король сам должен ошибиться."),
    (KNNK, "Двумя конями мат невозможен ни в какой позиции."),  # left unjudged: «невозможен» is often the forced mate
    (KRK, "Без края мата ладьёй не бывает."),
    (KRK, "Короля нужно прижать к краю — иначе мата ладьёй нет."),
    (KNNK, "Здесь мат возможен только на a8."),  # squares of this position, not of the ending
])
def test_true_or_unjudged_mate_places_pass(fen, sentence):
    assert check_sentence(sentence, _plain(fen)) == []


# ── piece_decides: the parts of the claim ────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence,piece", [
    ("всё решает ход ферзя.", chess.QUEEN),
    ("ферзём ты выигрываешь сразу.", chess.QUEEN),
    ("решающий удар наносит ферзь.", chess.QUEEN),
    ("победу здесь приносит ферзь.", chess.QUEEN),
    ("ферзь в одиночку решает всё.", chess.QUEEN),
    ("ферзь у белых решает.", chess.QUEEN),
    ("партию выигрывает ход ферзём.", chess.QUEEN),
    ("выигрывает ферзевая атака на короля e6.", chess.QUEEN),
    ("и решающее слово за ферзём.", chess.QUEEN),
    ("белые решают ладьёй.", chess.ROOK),
])
def test_outcome_claim_parts(sentence, piece):
    parts = _outcome_parts(sentence.replace("ё", "е"))
    assert parts is not None and parts[0] == piece, parts


@pytest.mark.parametrize("sentence", [
    "решает не ферзь, а конь.",
    "лишний конь решает партию.",
    "слон c4 и ферзь h5 решают.",
    "ферзь выигрывает пешку.",
    "конь решает задачу защиты.",
    "ферзь тут один ничего не решает.",
    "пешка h3 решает.",
    "решает активный король.",
    "решает ферзь вместе с ладьёй.",
    "ферзь, возможно, решает.",
    "твой ферзь выигрывает темп.",
])
def test_not_an_outcome_claim(sentence):
    assert _outcome_parts(sentence.replace("ё", "е")) is None


def test_the_claim_in_the_last_clause_is_read_past_a_denial_before_it():
    ctx = _plain("r1bq1b1r/ppp3pp/2n1k3/3np3/2B5/5Q2/PPPP1PPP/RNB1K2R w KQ - 2 8")
    s = "Мата нет, но король чёрных в центре, и всё решает ферзь."
    claims = _piece_claims(s.lower(), s, ctx)
    assert claims and claims[0]["piece"] == chess.QUEEN


@pytest.mark.parametrize("sentence", [
    "Ферзь выигрывает пешку f7.",
    "Конь решает задачу защиты f7.",
    "Активный ферзь решает.",
    "Решающую роль играет пешка.",
    "Ферзём чёрные выигрывают сразу.",  # not the side to move
])
def test_no_claim_on_the_board(sentence):
    assert _piece_claims(sentence.lower(), sentence, _plain(SCHOLAR)) == []


# ── trades ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _game(key: str) -> CheckContext:
    g = next(x for x in GAMES if x["key"] == key)
    ctx = CheckContext.from_fens([chess.STARTING_FEN], [_pgn(g)])
    ctx.language = "ru"
    return ctx


@pytest.mark.parametrize("key,sentence", [
    # an exchange inside a longer run of captures (review-fp R8)
    ("kasparov-topalov", "В партии Каспаров — Топалов белые отдали ладью за пешку: 24.Rxd4 cxd4."),
    ("kasparov-topalov", "Каспаров отдал ладью за пешку d4."),
    ("kasparov-topalov", "На 24-м ходу белые отдали ладью за пешку."),
    ("evergreen", "Белые отдали ладью за коня: 20.Rxe7+ Nxe7."),
    ("evergreen", "В Вечнозелёной партии Андерсен отдал ферзя за коня: 21.Qxd7+ Kxd7."),
    # a combination driven by checks is one trade (the windmill)
    ("game-of-the-century", "В Партии века Фишер отдал ферзя за ладью, двух слонов и пешку."),
    # the other frames, said truly
    ("wch2021-g6", "Карлсен получил две ладьи за ферзя."),
    ("wch2021-g6", "Непомнящий получил ферзя за две ладьи."),
    ("wch2021-g6", "Ферзь Карлсена был отдан за две ладьи."),
    ("wch2021-g6", "Был размен ферзя на две ладьи."),
    ("wch2021-g6", "Белые отдали ферзя, получив две ладьи."),
    ("wch2021-g6", "Размен ферзя на ладью выгоден белым."),  # no past: a line, not the game
    ("opera", "Чёрные получили двух слонов за коня."),  # the bishop pair
])
def test_true_trades_pass(key, sentence):
    assert trade_issues(sentence, _game(key)) == []


@pytest.mark.parametrize("key,sentence,needle", [
    ("wch2021-g6", "Там был размен ферзя на ладью.", "Neither side ever gave the queen for a rook"),
    ("wch2021-g6", "Был красивый размен: ферзь за ладью.", "26.Qxc8 Rxc8 27.Rxc8"),
    ("wch2021-g6", "Ферзь белых был отдан за ладью.", "White never gave the queen for a rook"),
    ("wch2021-g6", "Белые получили за ферзя только ладью.", "White never gave the queen for a rook"),
    ("wch2021-g6", "Чёрные получили ферзя за ладью.", "Black never gave a rook for the queen"),
    ("wch2021-g6", "Белые отдали ферзя, получив за него одну ладью.", "White never gave the queen for a rook"),
    ("wch2021-g6", "Белые отдали ферзя за ладью: 26.Qxc8 Rxc8.", "26.Qxc8 Rxc8 27.Rxc8"),  # not settled on c8
    ("kasparov-topalov", "Белые отдали ферзя за ладью: 24.Rxd4 cxd4.", "24.Rxd4"),  # the cited exchange named
])
def test_wrong_trades_are_cut(key, sentence, needle):
    issues = trade_issues(sentence, _game(key))
    assert issues and needle in issues[0], issues


def test_frames_normalise_to_giver_given_received():
    got = [(f["a"], f["b"], f["giver"]) for f in frames("Белые получили за ферзя только ладью.")]
    assert got == [(["Q"], ["R"], "subject")]
    got = [(f["a"], f["b"], f["giver"]) for f in frames("Ферзь белых был отдан за ладью.")]
    assert got == [(["Q"], ["R"], "owner")]
    assert frames("Размен ферзя на ладью выгоден белым.") == []
