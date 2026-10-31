"""P6 Records and rules (plan 31.10): trades told about a recorded game (src/trade_claims.py, detector ``trades``),
the famous games' exchanges as pairs (src/famous_games.py, E′), how the pieces move (src/rules_facts.py, D) and the
rules the board shows this turn (D′).

Rows: x-wc2021-g6 (must, caught — tests/unit/test_detect1031_rows.py replays it); sets_old «Карлсен впервые отдал
ладью за коня»; r-pawn-back and stalemate-hyp are prevention (their deterministic acceptance is here).
True controls: tests/fixtures/detect1031/negatives/P6.json, and the ones below.
"""
from __future__ import annotations

import time

import chess
import pytest

from src.answer_check import CheckContext, check_sentence
from src.famous_games import GAMES, _pgn, facts, famous_game
from src.rules_facts import rules_block
from src.trade_claims import claims, games_of, trade_issues


def _ctx(key: str, language: str = "ru") -> CheckContext:
    g = next(x for x in GAMES if x["key"] == key)
    ctx = CheckContext.from_fens([chess.STARTING_FEN], [_pgn(g)])
    ctx.language = language
    return ctx


def _live(moves: str, student=chess.WHITE) -> CheckContext:
    b = chess.Board()
    for m in moves.split():
        b.push_san(m)
    ctx = CheckContext.from_fens([b.fen()], [moves], student_color=student)
    ctx.game_moves = moves.split()
    ctx.language = "ru"
    return ctx


# ── E: trades against the score ─────────────────────────────────────────────────────────────────────────────────
def test_the_row_queen_for_a_rook_names_the_real_exchange():
    s = ("Хочешь, пройдём по ключевым моментам этой партии — там был красивый размен, где белые отдали ферзя за ладью "
         "и получили решающий эндшпиль?")
    issues = trade_issues(s, _ctx("wch2021-g6"))
    assert len(issues) == 1
    assert "White never gave the queen for a rook" in issues[0]
    # the antidote (tests/fixtures/prevent/antidotes.json, issue "two rooks|Rxc8")
    assert "26.Qxc8 Rxc8 27.Rxc8 — White gave the queen for two rooks" in issues[0]


def test_sets_old_rook_for_a_knight_black_had_none_left():
    s = "Хочешь, пройдёмся по ходам с 79-го — там Карлсен впервые отдал ладью за коня, и это был тот самый перелом?"
    issues = trade_issues(s, _ctx("wch2021-g6"))
    assert issues and "White never gave a rook for a knight" in issues[0]
    assert "80.Rxf7+ Kxf7 81.Rb7+ Kg6 82.Rxa7 — White gave a rook for a bishop and a pawn" in issues[0]


def test_nearest_exchange_queen_for_a_knight_in_the_opera_game():
    """[J] the nearest exchange by unit overlap: the queen went for nothing (16.Qb8+ Nxb8 17.Rd8#), not the long run
    13.Rxd7 … Nxb8 that has a knight in it."""
    issues = trade_issues("Белые отдали ферзя за коня.", _ctx("opera"))
    assert issues == ["In Opera Game (Оперная партия), White never gave the queen for a knight: 16.Qb8+ Nxb8 17.Rd8# — "
                      "White gave the queen and got nothing back for it, and the mate followed."]


def test_nearest_exchange_takes_neighbouring_runs_for_two_units():
    issues = trade_issues("Андерсен отдал обе ладьи за слона.", _ctx("immortal"))
    assert issues and "18...Bxg1 19.e5 Qxa1+ — White gave two rooks and got nothing back for it" in issues[0]


@pytest.mark.parametrize("key,sentence", [
    ("wch2021-g6", "Там белые отдали ферзя за две ладьи: 26.Qxc8 Rxc8 27.Rxc8."),
    ("wch2021-g6", "На 80-м ходу белые отдали ладью за слона."),        # pawns ignored unless named
    ("wch2021-g6", "Чёрные отдали коня за слона."),                     # 17.Bxf6 gxf6
    ("wch2021-g6", "Карлсен отдал ладью за пешку и слона."),            # «за пешку и слона» past «и»
    ("wch2021-g6", "Непомнящий получил ферзя за две ладьи."),           # «получил»: not read (the bishop pair class)
    ("opera", "Чёрные получили двух слонов за коня."),                    # the bishop pair, an imbalance
    ("opera", "Белые отдали коня за двух слонов."),
    ("wch2021-g6", "Чёрные разменяли две ладьи на ферзя."),
    ("wch2021-g6", "Карлсен отдал качество за пешку."),                # the exchange: R for a minor (+ a pawn)
    ("opera", "Морфи отдал ладью за коня."),                             # 13.Rxd7 Rxd7
    ("opera", "Морфи отдал коня за две пешки."),                         # 10.Nxb5 cxb5 11.Bxb5+
    ("opera", "Белые отдали коня за пешку."),                            # a bare «пешку»: at least one
    ("opera", "Морфи пожертвовал ферзя за мат."),                        # not a unit
    ("opera", "Морфи отдал ферзя, и следующим ходом последовал мат."),   # no «за»
    ("wch2021-g6", "Если бы белые отдали ферзя за ладью, позиция была бы проиграна."),
    ("wch2021-g6", "Белые не отдали ферзя за ладью."),
    ("wch2021-g6", "В партии Таль — Ботвинник белые отдали ферзя за ладью."),  # another game
    ("wch2021-g6", "В оперной партии белые отдали ферзя за коня."),           # a famous game the turn has no score of
    ("wch2021-g6", "Они отдали ферзя за ладью."),                              # no subject
    ("wch2021-g6", "Обычно в таких позициях белые отдавали ферзя за ладью."),
    ("immortal", "Андерсен отдавал фигуру за фигурой, и каждая жертва отнимала у короля поле."),  # corpus_pos immortal
])
def test_true_or_undecided_claims_pass(key, sentence):
    assert trade_issues(sentence, _ctx(key)) == []


def test_a_line_told_is_not_the_game():
    ctx = _live("e4 e5 Nf3 Nc6 Bb5 a6 Bxc6 dxc6")
    assert trade_issues("После Bxc6 bxc6 ты отдал коня за слона.", ctx) == []  # bxc6: not the game's move
    ctx.scene_san, ctx.scene_age = "Ba4", 1  # the answer just wrote a move the game never had
    assert trade_issues("Выходит, ты отдал коня за слона.", ctx) == []
    ctx.scene_san, ctx.scene_age = "Bxc6", 0  # the game's own move
    assert trade_issues("Выходит, ты отдал коня за слона.", ctx)


def test_english_claims():
    ctx = _ctx("wch2021-g6", "en")
    assert trade_issues("On move 26 White gave up the queen for two rooks.", ctx) == []
    assert trade_issues("Black won the queen for two rooks.", ctx) == []
    issues = trade_issues("White gave up the queen for a rook.", ctx)
    assert issues and "two rooks" in issues[0]


def test_the_game_on_the_board_is_judged():
    ctx = _live("e4 e5 Nf3 Nc6 Bb5 a6 Bxc6 dxc6")
    assert trade_issues("Ты отдал слона за коня.", ctx) == []
    issues = trade_issues("Ты отдал коня за слона.", ctx)
    assert issues and issues[0].startswith("In this game, White never gave a knight for a bishop (White lost no "
                                           "knight in it)")
    assert "4.Bxc6 dxc6 — White gave a bishop for a knight" in issues[0]


def test_no_record_no_verdict():
    ctx = CheckContext.from_fens(["2r3k1/5ppp/8/8/8/8/5PPP/2RR2K1 b - - 0 1"])
    assert games_of(ctx) == []
    assert trade_issues("Белые отдали ферзя за две ладьи.", ctx) == []
    # a short opening line from the start is not a game
    ctx = CheckContext.from_fens([chess.STARTING_FEN], ["1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Bxc6 dxc6"])
    assert games_of(ctx) == [] and trade_issues("Белые отдали коня за слона.", ctx) == []


def test_a_partial_record_of_a_famous_game_is_judged_by_its_whole_score():
    g = next(x for x in GAMES if x["key"] == "wch2021-g6")
    first = " ".join(g["moves"].split()[:30])  # moves 1–20 only
    ctx = CheckContext.from_fens([chess.STARTING_FEN], [first])
    found = games_of(ctx)
    assert [x["key"] for x in found] == ["wch2021-g6"] and len(found[0]["moves"]) == 271
    assert trade_issues("Там белые отдали ферзя за две ладьи.", ctx) == []


def test_claim_parsing():
    (m, a, b, rev), = claims("где белые отдали ферзя за ладью и получили решающий эндшпиль")
    assert (a, b, rev) == (["Q"], ["R"], False)
    (m, a, b, rev), = claims("Карлсен отдал ладью за пешку и слона")
    assert a == ["R"] and b == ["P+", "B"]
    assert claims("чёрные получили две ладьи за ферзя") == []
    assert claims("чёрные получили двух слонов за коня") == []
    assert claims("белые отдали пешку за быструю атаку") == []
    assert claims("отдал фигуру ни за что") == []


def test_switch_off_and_shadow(monkeypatch, caplog):
    s = "там белые отдали ферзя за ладью."
    monkeypatch.setenv("COACH_DETECTORS_OFF", "trades")
    assert trade_issues(s, _ctx("wch2021-g6")) == []
    monkeypatch.delenv("COACH_DETECTORS_OFF")
    monkeypatch.setenv("COACH_DETECTORS_SHADOW", "trades")
    with caplog.at_level("INFO", logger="src.trade_claims"):
        assert trade_issues(s, _ctx("wch2021-g6")) == []
    assert any("trades shadow" in r.message for r in caplog.records)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW")
    assert trade_issues(s, _ctx("wch2021-g6"))


def test_lesson_tutor_gets_no_trade_check():
    ctx = _ctx("wch2021-g6")
    ctx.relation_surface = "lesson"
    assert trade_issues("там белые отдали ферзя за ладью.", ctx) == []


def test_through_the_answer_check():
    issues = check_sentence("Там белые отдали ферзя за ладью.", _ctx("wch2021-g6"))
    assert any("White never gave the queen for a rook" in i for i in issues)


def test_latency():
    ctx = _ctx("wch2021-g6")
    s = "там белые отдали ферзя за ладью."
    trade_issues(s, ctx)
    times = []
    for _ in range(9):
        t = time.perf_counter()
        trade_issues(s, ctx)
        times.append((time.perf_counter() - t) * 1000)
    assert sorted(times)[4] < 50  # 271 plies, cached exchanges (the bound is loose: a shared machine)
    t = time.perf_counter()
    for _ in range(200):
        trade_issues("Конь f3 прыгает на g5, и белые получают атаку.", ctx)
    assert (time.perf_counter() - t) * 1000 / 200 < 1.0  # no trade claim: one regex


# ── E′: the famous games' exchanges as pairs ────────────────────────────────────────────────────────────────────
def test_famous_game_facts_pair_the_exchanges(monkeypatch):
    g6 = next(x for x in GAMES if x["key"] == "wch2021-g6")
    text = facts(g6)
    assert "26.Qxc8 Rxc8 27.Rxc8: White gave the queen for two rooks" in text  # antidote of x-wc2021-g6
    assert "80.Rxf7+ Kxf7 81.Rb7+ Kg6 82.Rxa7: White gave a rook for a bishop and a pawn" in text
    assert "Pieces White lost" not in text
    opera = next(x for x in GAMES if x["key"] == "opera")
    assert "16.Qb8+ Nxb8 17.Rd8#: White gave the queen for nothing, and mate followed" in facts(opera)
    block = famous_game("Покажи 6-ю партию матча Карлсен — Непомнящий 2021 года")["block"]
    assert "queen for two rooks" in block
    monkeypatch.setenv("COACH_TURN_FACTS", "0")
    assert facts(g6).startswith("Pieces White lost: ")  # as before 31.10


def test_every_famous_game_has_russian_player_names():
    for g in GAMES:
        assert g.get("white_ru") and g.get("black_ru"), g["key"]


# ── D: how the pieces move ──────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("question", ["Может ли пешка ходить назад?", "Can a pawn move backwards?",
                                      "Пешка артқа жүре ала ма?"])
def test_the_pawn_rule_for_the_three_languages(question):
    block = rules_block(question)
    assert "captures one square diagonally forward, so every capture moves it to the next file" in block


@pytest.mark.parametrize("question,rule", [
    ("Как ходит конь?", "Knight:"), ("Может ли слон перепрыгнуть через фигуру?", "Bishop:"),
    ("Можно ли королю ходить под шах?", "King:"), ("Can the rook move diagonally?", "Rook:"),
])
def test_a_piece_rule(question, rule):
    assert rule in rules_block(question)


@pytest.mark.parametrize("question", [
    "Какой ход лучше?", "Может ли мой конь взять слона на f6?", "Можно ли сейчас сыграть конём на f3?",
    "Покажи пример связки", "Повтори, пожалуйста, можно?", "А конец партии какой?", "Почему королевский гамбит?",
    "Патша қай жерде? Бұл ереже ме?",
    "Можно ли взять на проходе слоном или конём?",  # the en passant rule, not how a bishop moves
])
def test_no_movement_rule_for_board_questions(question):
    block = rules_block(question)
    assert not any(r in block for r in ("Pawn:", "Knight:", "Bishop:", "Rook:", "Queen:", "King:"))


def test_movement_rules_follow_the_facts_switch(monkeypatch):
    monkeypatch.setenv("COACH_TURN_FACTS", "0")
    assert rules_block("Может ли пешка ходить назад?") == ""
    assert "Stalemate" in rules_block("Пат — это ничья?")  # the old rules stay


# ── D′: the rules the board shows ───────────────────────────────────────────────────────────────────────────────
STALEMATE = {"fen": "k7/8/3Q4/8/8/8/8/2K5 w - - 0 1", "ideas": [{"san": "Qb6", "draw": True}], "idea_fens": [],
             "engine_lines": [{"moves": ["Qd7", "Kb8", "Kd2"], "eval": "#7"}]}


def test_stalemate_idea_gives_the_rule_and_the_engine_moves_fact():
    block = rules_block("Хочу сыграть Qb6, чтобы запереть короля. Хорошо?", board_verdicts=STALEMATE)
    assert "Stalemate: the side to move has no legal move and is not in check" in block
    assert "a check is not required" in block
    assert "after Qb6 Black is not in check and has no legal move: stalemate" in block
    assert "after Qd7 Black is not in check and has 1 legal move (Kb8) — the engine's move" in block


def test_verdict_rules_never_repeat_the_questions_rule():
    block = rules_block("Пат — это ничья? Хочу Qb6", board_verdicts=STALEMATE)
    assert "Stalemate: the side" not in block and "a check is not required" in block and "after Qd7" in block


def test_verdict_rules_mate_castling_and_nothing():
    mate = {"fen": "6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1", "ideas": [{"san": "Ra8#", "mate": True}], "engine_lines": []}
    assert "Checkmate: the king is in check" in rules_block("А если Ra8?", board_verdicts=mate)
    castle = {"fen": "r3k2r/8/8/8/8/8/5b2/R3K2R w KQkq - 0 1", "ideas": [], "engine_lines": []}
    block = rules_block("Можно рокироваться?", board_verdicts=castle)
    assert "Castling is illegal only if" in block and "On this board" not in block  # the board facts say why
    assert rules_block("0-0", board_verdicts=castle) == ""  # a move in a game, not a question
    quiet = {"fen": chess.STARTING_FEN, "ideas": [{"san": "e4"}], "engine_lines": [{"moves": ["e4", "e5"]}]}
    assert rules_block("Какой ход лучше?", board_verdicts=quiet) == ""
    assert rules_block("Пат?", board_verdicts={"fen": None, "ideas": [{"san": "Qb4", "draw": True}]}) == ""
    assert rules_block("Пат?", board_verdicts={"fen": "garbage", "ideas": []}) == ""


def test_verdict_rules_follow_the_facts_switch(monkeypatch):
    monkeypatch.setenv("COACH_TURN_FACTS", "0")
    assert rules_block("Хочу сыграть Qb6", board_verdicts=STALEMATE) == ""
