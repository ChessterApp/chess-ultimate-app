"""fix1102 K4: rule talk is not a claim about the board in front of the student (verify1102 §6.2).

Live 02.11 the answer check judged nine true sentences against the current board: castling conditions («Рокировка
разрешена, только если …», "you can't castle while your king is in check", «Она теряется только в четырёх случаях:
…, король под шахом прямо сейчас, …»), a notation example («К:d5 — конь берёт на d5»), eval signs («+− — белые
выигрывают»), «сам король под шахом не стоит» and «атакованное поле b1 рокировку не отменяет». The tests below use new
boards and new wordings; each positive case is also shown to be flagged with the scope switched off, so it tests the
mechanism and not a lucky miss.
"""
from __future__ import annotations

import chess
import pytest

from src import answer_check as ac
from src import config
from src.claim_scope import denied_after, rule_spans, without_spans

# White has moved its king and back (no castling rights), nothing between king and rooks, not in check.
NO_RIGHTS = "r3k2r/ppqb1ppp/2nbpn2/3p4/3P4/2NBPN2/PPQB1PPP/R3K2R w kq - 6 10"
# A quiet middlegame, nobody in check.
QUIET = "r1bq1rk1/pp2bppp/2n1pn2/2pp4/3P4/2PBPN2/PP1N1PPP/R1BQ1RK1 w - - 0 8"
# After 1.e4 e5: no knight can take on a7 or h6.
OPEN = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
# Stalemate: Black king h8, White queen f7, White king g6; Black to move, not in check.
STALEMATE = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"


def _ctx(fen, question="", student=chess.WHITE, eval_=None):
    ctx = ac.CheckContext.from_fens([fen], question=question, student_color=student)
    if eval_ is not None:
        ctx.engine_eval = eval_
    return ctx


def _check(sentence, fen, **kw):
    return ac.check_sentence(sentence, _ctx(fen, **kw))


@pytest.fixture
def scope_on(monkeypatch):
    monkeypatch.delenv("COACH_DETECTORS_OFF", raising=False)
    monkeypatch.delenv("COACH_DETECTORS_SHADOW", raising=False)
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")


def _off(monkeypatch):
    monkeypatch.setenv("COACH_DETECTORS_OFF", "rule_scope")


# ── rule talk: left unjudged on the board (and flagged as before with the switch off) ─────────────────────────────

RULE_TALK = [
    # castling conditions stated as a law, on a board where White cannot castle
    ("Длинная рокировка возможна, лишь когда ни король, ни эта ладья ни разу не ходили; шах тут ни при чём.", NO_RIGHTS, {}),
    # the cases of a law listed after a colon, a «now» inside the list
    ("Рокировка запрещена в трёх случаях: король под шахом в данный момент, король проходит через битое поле, "
     "король встаёт на битое поле.", QUIET, {}),
    # English, a prohibition with «while»
    ("Castling is illegal while your king is in check.", QUIET, {"question": "What are the castling rules?"}),
    # a notation definition with its examples (no knight can take on e5 or d4 here)
    ("Буква x в записи означает взятие: Nxa7 — конь бьёт на a7, Nxh6 — конь бьёт на h6.", OPEN, {}),
    # eval signs defined, the engine says +0.2
    ("Символ −+ обозначает решающий перевес: чёрные выигрывают, а +− — белые выигрывают.", QUIET, {"eval_": 0.2}),
    # a term defined
    ("Шах — это ситуация, при которой король под ударом фигуры соперника.", QUIET, {}),
]


@pytest.mark.parametrize("sentence,fen,kw", RULE_TALK)
def test_rule_talk_is_not_judged_on_the_board(scope_on, monkeypatch, sentence, fen, kw):
    assert _check(sentence, fen, **kw) == []
    _off(monkeypatch)
    assert _check(sentence, fen, **kw), "the case must exercise the scope: without it the board check flags it"


def test_the_shadow_mode_records_and_keeps_the_old_verdict(scope_on, monkeypatch):
    monkeypatch.setenv("COACH_DETECTORS_SHADOW", "rule_scope")
    ctx = _ctx(QUIET)
    assert ac.check_sentence("Castling is illegal while your king is in check.", ctx)
    assert any(r[0] == "rule_scope" for r in ctx.detector_shadow)


# ── still judged: the sentence is pinned to this board ────────────────────────────────────────────────────────────

def test_a_now_word_in_the_head_keeps_the_board_claim(scope_on):
    issues = _check("Сейчас короткая рокировка возможна, только если ты не боишься атаки на королевском фланге.",
                    NO_RIGHTS)
    assert any("cannot castle" in i for i in issues)


def test_a_plain_board_claim_is_judged(scope_on):
    assert any("not in check" in i for i in _check("Твой король под шахом, поэтому рокировка невозможна.", QUIET))
    assert any("Nxa7" in i for i in _check("Ход Nxa7 выигрывает пешку.", OPEN))


def test_a_sign_pinned_to_this_position_is_judged(scope_on):
    issues = _check("Знак +− здесь означает, что белые выигрывают.", QUIET, eval_=0.2)
    assert any("not winning" in i for i in issues)


def test_a_square_in_a_law_frame_keeps_it_on_the_board():
    text = "Слона d3 можно взять, только если конь f3 уйдёт."
    assert rule_spans(text) == []


def test_a_yes_no_answer_keeps_its_head_and_hides_the_condition():
    text = "Нет — рокироваться нельзя, пока король под шахом."
    spans = rule_spans(text, anchored_answer=True)
    assert spans and without_spans(text, spans).startswith("Нет — рокироваться нельзя")
    assert "под шахом" not in without_spans(text, spans)
    assert without_spans(text, rule_spans(text)).strip() == ""


def test_while_after_can_is_not_a_law():
    assert rule_spans("The rook can attack the pawn while the king walks over.") == []


def test_the_game_record_is_not_notation_talk():
    assert rule_spans("Запись партии показывает, что ты сыграл слоном.") == []


# ── a state denied by the copula after it ─────────────────────────────────────────────────────────────────────────

def test_check_denied_after_the_state(scope_on):
    assert _check("Чёрный король под шахом не стоит, но ходить ему некуда — это пат.", STALEMATE,
                  student=chess.WHITE) == []


def test_check_asserted_before_another_denial_is_judged(scope_on):
    issues = _check("Чёрный король под шахом не может уйти на g8.", STALEMATE, student=chess.WHITE)
    assert any("black king is not in check" in i for i in issues)


def test_denied_after_reads_only_a_copula():
    t = "король под шахом не стоит"
    assert denied_after(t, t.index(" не"))
    t2 = "король под шахом не может уйти"
    assert not denied_after(t2, t2.index(" не"))


# ── the attacked b1/b8 square: the rule itself is not its opposite ───────────────────────────────────────────────

def test_attacked_b8_said_not_to_stop_castling(scope_on):
    assert _check("Атакованное поле b8 длинной рокировке чёрных не мешает.", QUIET) == []


def test_attacked_b1_said_to_forbid_castling_is_flagged(scope_on):
    issues = _check("При длинной рокировке атакованное поле b1 её запрещает.", QUIET)
    assert any("b1 (b8) must just be empty" in i for i in issues)


def test_the_law_detectors_read_the_hidden_rule_talk(scope_on):
    # A wrong law inside a law frame is still judged as a law: the rook may be attacked.
    issues = _check("Рокироваться разрешено, только если ладья не под боем и король не ходил.", QUIET,
                    question="Можно ли рокироваться, если ладья под боем?")
    assert any("castling is allowed when the rook is attacked" in i for i in issues)


# White may castle short here (nothing between, not in check, f1/g1 safe).
CAN_SHORT = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"


def test_a_yes_no_answer_about_this_board_keeps_its_claim(scope_on):
    # The condition after "while" is a rule; the answer «No — you can't castle short» is about this board and wrong.
    issues = _check("No — you can't castle short while your king is in check.", CAN_SHORT,
                    question="Can I castle short now?")
    assert any("can castle O-O" in i for i in issues)
    assert not any("not in check" in i for i in issues)


def test_the_same_rule_as_a_rule_is_left_alone(scope_on):
    assert _check("You can't castle short while your king is in check.", CAN_SHORT,
                  question="What are the rules of castling?") == []
