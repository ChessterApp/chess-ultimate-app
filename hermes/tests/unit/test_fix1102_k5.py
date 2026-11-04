"""fix1102 K5 — defender lists and attack parsing (VERDICT verify1102 §6.3 and the misparses).

Every case is on a NEW board with a NEW wording (not the reported sentences): true sentences must not be flagged,
false ones of the same shape must still be.

  * «X нападает на Y, её защищают Z и W»: the defenders were read as X's targets (the targets ran past a clause that
    has a verb and a subject of its own: an object pronoun with a verb, a participle, a gerund, a move on);
  * «Y под ударом X, но её защищает Z»: «под ударом» is the passive — the pronoun is Y, not the attacker X;
  * a plural verb agrees with a plural subject after it: «e5 держат пешки d6 и f6», «его защищают пешки b7 и d7»;
  * a pin names the piece behind: it is reached through the pinned piece, not blocked by it;
  * «exd4 … : exd4» — the same move named again after words is no recapture;
  * «2...e6: e6 —» — a colon with a space after it is punctuation, not a capture «e6xe6»;
  * «Мой первый ход — пешка с c2 пошла на c4» — the move told in words is c4, not «c2»;
  * «дать шах ферзём с a5» — the queen acting from a square it can go to: two readings, not judged;
  * «нападёт» — a perfective future is about the board after a move, not about the board now;
  * "the knight checks the king and attacks the rook" — the king is the object of «checks», not the subject.
"""
import chess
import pytest

from src import claim_grammar
from src.answer_check import CheckContext, check_sentence


def _fen(moves: str) -> str:
    b = chess.Board()
    for m in moves.split():
        b.push_san(m)
    return b.fen()


def _ctx(fen: str) -> CheckContext:
    return CheckContext.from_fens([fen], [], question="")


def _game(moves: str, student: str) -> CheckContext:
    mv = moves.split()
    ctx = _ctx(_fen(moves))
    first = 0 if student == "black" else 1
    ctx.game_engine_moves = [m for i, m in enumerate(mv) if i % 2 == first]
    ctx.game_moves = mv
    ctx.student_color = chess.WHITE if student == "white" else chess.BLACK
    return ctx


ITALIAN = _fen("e4 e5 Nf3 Nc6")
RUY = _fen("e4 e5 Nf3 Nc6 Bb5")
RUY_D6 = _fen("e4 e5 Nf3 Nc6 Bb5 d6")
RUY_A6 = _fen("e4 e5 Nf3 Nc6 Bb5 a6")
VIENNA = _fen("e4 e5 Nc3 Nf6")


# ── defender lists after an attack: the defenders are no targets ─────────────────────────────────────────────────

@pytest.mark.parametrize("fen,sentence", [
    (ITALIAN, "Конь f3 нападает на пешку e5, её защищает конь c6."),
    (ITALIAN, "Конь f3 бьёт пешку e5, а её держит конь c6."),
    (RUY, "Слон b5 нападает на коня c6, его защищают пешки b7 и d7."),
    (RUY, "Слон b5 атакует коня c6, защищает его пешка b7."),
    (ITALIAN, "Конь f3 нападает на пешку e5, защищённую конём c6."),
    (_fen("e4 e5 Qh5 Nc6"), "Ферзь h5 смотрит на пешку f7, её охраняет король e8."),
    (_fen("e4 e5 d4 Nc6"), "Пешка d4 нападает на пешку e5, открывая слону c1 дорогу на g5."),
    (_fen("d4 d5 c4 c6"), "Пешка c6 держит d5, оставляя слону c8 выход на f5."),
])
def test_a_defender_list_is_not_read_as_targets(fen, sentence):
    assert check_sentence(sentence, _ctx(fen)) == []


@pytest.mark.parametrize("fen,sentence,needle", [
    # the defender named is wrong: still judged, as the defender's claim
    (ITALIAN, "Конь f3 нападает на пешку e5, её защищает слон c8.", "c8"),
    # the attack itself is wrong: still judged
    (RUY, "Слон b5 нападает на пешку e5, её защищает конь c6.", "e5"),
    # two targets of one attack: the second is still a target
    (ITALIAN, "Конь f3 нападает на пешку e5 и на пешку f7.", "f7"),
])
def test_a_wrong_attack_or_defence_is_still_flagged(fen, sentence, needle):
    issues = check_sentence(sentence, _ctx(fen))
    assert issues and any(needle in i for i in issues), issues


@pytest.mark.parametrize("sentence", [
    "Пешка e4 под ударом коня f6, но её защищает конь c3.",
    "Пешка e4 под атакой коня f6, её прикрывает конь c3.",
])
def test_under_attack_is_the_passive_for_the_pronoun(sentence):
    assert check_sentence(sentence, _ctx(VIENNA)) == []


def test_under_attack_with_a_wrong_defender_is_flagged():
    issues = check_sentence("Пешка e4 под ударом коня f6, но её защищает слон f1.", _ctx(VIENNA))
    assert any("f1" in i for i in issues), issues


# ── the plural verb agrees with the plural subject after it ──────────────────────────────────────────────────────

def _claims(sentence):
    return [(c.rel, c.subj.sq, tuple(o.sq for o in c.objs)) for c in claim_grammar.extract(sentence, {}, "ru")]


def test_a_square_before_a_plural_verb_is_its_object():
    claims = _claims("e5 держат пешки d6 и f6.")
    assert ("hold", "d6", ("e5",)) in claims and ("hold", "f6", ("e5",)) in claims, claims
    assert not any(c[1] == "e5" for c in claims), claims


def test_a_side_before_a_plural_verb_keeps_its_object():
    assert not any(c[1] in ("d5", "c6") for c in _claims("Белые атакуют пешки d5 и c6."))


def test_a_coordinated_subject_is_plural():
    claims = _claims("Конь и слон защищают пешку e4.")
    assert {c[0] for c in claims} == {"defend"} and all(c[2] == ("e4",) for c in claims), claims


@pytest.mark.parametrize("fen,sentence", [
    ("4k3/8/3p1p2/4p3/8/8/8/4K3 w - - 0 1", "e5 держат пешки d6 и f6."),
    (RUY, "Слон b5 нацелен на коня c6, его защищают пешки b7 и d7."),
])
def test_plural_defenders_after_the_verb_are_not_flagged(fen, sentence):
    assert check_sentence(sentence, _ctx(fen)) == []


def test_plural_defenders_that_do_not_defend_are_flagged():
    issues = check_sentence("e5 держат пешки d6 и h6.", _ctx("4k3/8/3p3p/4p3/8/8/8/4K3 w - - 0 1"))
    assert any("h6" in i for i in issues), issues


# ── a pin names the piece behind it ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sentence", [
    "The bishop on b5 pins the knight on c6 to the king on e8.",
    "Слон b5 держит коня c6 в связке с королём e8.",
    "Слон b5 связывает коня c6 с королём e8.",
])
def test_an_absolute_pin_is_no_blocked_line(sentence):
    assert check_sentence(sentence, _ctx(RUY_D6)) == []


def test_a_pin_through_two_pieces_is_still_flagged():
    # the d7 pawn stands between c6 and e8 too: nothing is pinned
    issues = check_sentence("The bishop on b5 pins the knight on c6 to the king on e8.", _ctx(RUY_A6))
    assert any("e8" in i for i in issues), issues


# ── written moves ────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_same_move_named_again_is_no_recapture():
    sentence = "Лучший ответ чёрных — exd4, то есть просто взять пешку: exd4."
    assert check_sentence(sentence, _ctx(_fen("e4 e5 d4"))) == []


def test_a_colon_with_a_space_is_no_capture():
    assert check_sentence("Надёжнее всего 2...e6: e6 — пешка поддерживает центр.", _ctx(_fen("d4 d5 c4"))) == []


def test_a_tight_colon_capture_is_still_judged():
    issues = check_sentence("Белые могут сыграть e4:e5.", _ctx(_fen("e4 d5")))
    assert any("e4xe5" in i for i in issues), issues


def test_a_move_told_from_to_names_its_destination():
    ctx = _game("c4", "black")
    assert check_sentence("Мой первый ход — пешка с c2 пошла на c4: белые берут под контроль поле d5.", ctx) == []
    ctx = _game("d4 Nf6", "white")
    assert check_sentence("Мой ответ — конь с g8 вышел на f6.", ctx) == []


def test_a_wrong_move_told_from_to_is_flagged_by_its_destination():
    issues = check_sentence("Мой первый ход — пешка с e2 пошла на e4.", _game("c4", "black"))
    assert any("did not play e4" in i for i in issues), issues


# ── «ферзём с a5»: from a square the piece can go to ─────────────────────────────────────────────────────────────

def test_check_from_a_square_the_queen_can_reach_is_not_judged():
    assert check_sentence("Чёрные могут дать шах ферзём с a5.", _ctx(_fen("d4 c6 e4"))) == []


def test_an_instrument_no_piece_can_reach_is_still_flagged():
    issues = check_sentence("Белые бьют пешку h7 ладьёй с h3.", _ctx(_fen("e4 e5")))
    assert any("no rook on h3" in i for i in issues), issues


# ── tense: «нападёт» is after a move ─────────────────────────────────────────────────────────────────────────────

def test_a_future_attack_is_not_judged_on_the_board_now():
    assert check_sentence("Оттуда слон нападёт на пешку f7.", _ctx(ITALIAN)) == []


def test_a_present_attack_on_an_unattacked_piece_is_flagged():
    issues = check_sentence("Слон нападает на пешку f7.", _ctx(ITALIAN))
    assert any("f7" in i for i in issues), issues


# ── English: the object of the first verb is not the subject of the second ───────────────────────────────────────

FORK = "r3kb1r/ppN2ppp/8/8/8/8/PPP2PPP/R3KB1R b KQkq - 0 1"


def test_a_coordinated_predicate_keeps_its_subject():
    assert check_sentence("Nxc7+ is a fork: the knight checks the king and attacks the rook on a8.", _ctx(FORK)) == []


def test_a_coordinated_predicate_with_a_wrong_target_is_flagged():
    issues = check_sentence("Nxc7+ is a fork: the knight checks the king and attacks the rook on h8.", _ctx(FORK))
    assert any("h8" in i for i in issues), issues


# ── the /learn tutor keeps its own readings ──────────────────────────────────────────────────────────────────────

def test_the_lesson_tutor_reads_as_before():
    ctx = _ctx(ITALIAN)
    ctx.relation_surface = "lesson"
    # the 31.10 reading (the defender as a target) stays for the lesson tutor: its check is the team's, untouched
    assert check_sentence("Конь f3 нападает на пешку e5, её защищает конь c6.", ctx) != []
