"""The relation checker after the three reviews of attack-1030 (30.10: false positives, misses, wiring): each class
of error a review found, closed by a mechanism, with a true sentence that must stay unflagged (negative) and a false
one that must be caught (positive) next to it.

The answers run sentence by sentence through ``check_sentence`` in shadow mode (recorded, nothing cut — the state
goes on as on the page); the tests look at what the relation checker recorded for each sentence.
"""
import json

import chess
import pytest

from src import answer_check_relations as acr
from src import claim_grammar, claim_scene, config
from src.answer_check import CheckContext, _split_sentences, check_sentence

IT = "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"  # e4 e5 Nf3 Nc6 Bc4 Bc5
IT_GAME = "e4 e5 Nf3 Nc6 Bc4 Bc5".split()
TWO_KNIGHTS = "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
ST4 = "rnbqkb1r/pppppppp/5n2/8/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 1 2"  # d4 Nf6
SICILIAN = "r1bqkb1r/pp1p1ppp/2n2n2/4p3/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 0 6"


def _sentences(text):
    done, rest = _split_sentences(text + " ")
    return [s for s in done + [rest] if s.strip()]


def _flags(text, fen, game=None, question="", student=None, solution=None):
    """[(sentence, relation issues)] of *text* on its board, read in order."""
    lines = [" ".join(game)] if game else []
    ctx = CheckContext.from_fens([fen], lines=lines, question=question, student_color=student)
    if game:
        ctx.game_moves = list(game)
    if solution:
        acr.add_solution_line(ctx, list(solution))
    out = []
    for s in _sentences(text):
        before = len(ctx.relation_shadow)
        check_sentence(s, ctx)
        out.append((s.strip(), [i for _, issues in ctx.relation_shadow[before:] for i in issues]))
    return out


def _of(flags, fragment):
    got = [v for k, v in flags if fragment in k]
    assert got, f"no sentence holds {fragment!r}: {[k for k, _ in flags]}"
    return got[0]


@pytest.fixture(autouse=True)
def _shadow(monkeypatch):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "shadow")


# ── review:fp 1 — English «, and the X …»: the next clause's subject is no object ─────────────────────────────────
def test_the_next_clause_subject_is_not_an_object():
    flags = _flags("The knight on f3 attacks e5 and the knight on c6 defends it. "
                   "The bishop on c4 eyes f7, and the bishop on c5 eyes f2.", IT, question="Explain.")
    assert all(v == [] for _, v in flags), flags
    assert _flags("The rook attacks the bishop, and the king defends it.", "8/8/4k3/4b3/8/8/8/4R1K1 w - - 0 1",
                  question="Explain.")[0][1] == []
    # …the first clause is still judged, and so is a list of real objects
    flags = _flags("The knight on f3 attacks d5, and the knight on c6 defends e5. "
                   "The knight on f3 attacks the pawn on e5 and the bishop on c5.", IT, question="Explain.")
    assert _of(flags, "attacks d5")
    assert _of(flags, "and the bishop on c5")


def test_english_it_is_not_the_subject_of_its_own_verb():
    fen = "rnbqkb1r/pp3ppp/3ppn2/2p5/2B1P3/5N2/PPPP1PPP/RNBQ1RK1 w kq - 2 5"
    flags = _flags("The pawn on e6 is attacked. The knight on f6 defends it.", fen, question="x")
    assert "does not defend Black's pawn on e6" in _of(flags, "knight on f6 defends it")[0]
    # «it» after a square named in the sentence may be the square: no verdict
    flags = _flags("The knight on c3 defends e4, and the knight on f6 attacks it.", SICILIAN, question="x")
    assert _of(flags, "attacks it") == []
    # «it» as a subject goes on with the previous subject
    fen = "r1b1kb1r/pppp1ppp/2n5/4p3/2BnP1q1/5N2/PPPP1PPP/RNBQ1RK1 w kq - 0 6"
    flags = _flags("The knight on d4 attacks your knight on f3, and it also eyes c2 and e2.", fen, question="x")
    assert _of(flags, "it also eyes") == []
    flags = _flags("The knight on d4 attacks your knight on f3, and it also eyes c3.", fen, question="x")
    assert "knight on d4" in _of(flags, "it also eyes")[0]


# ── review:fp 2 — «Нет, X …» answers the question, it negates nothing ──────────────────────────────────────────────
def test_an_answer_word_negates_nothing():
    flags = _flags("Нет, конь f6 нападает на пешку e4. Нет-нет, конь f6 атакует e4. Нет: слон c4 атакует f7.",
                   TWO_KNIGHTS, question="Конь f6 защищает e4?")
    assert all(v == [] for _, v in flags), flags
    flags = _flags("Нет, конь f6 не нападает на пешку e4.", TWO_KNIGHTS, question="Конь f6 защищает e4?")
    assert "attacks White's pawn on e4" in _of(flags, "не нападает")[0]
    # a denial of «defends» on a square an enemy piece stands on says nothing about control
    assert _of(_flags("Конь f6 не защищает e4.", TWO_KNIGHTS, question="x"), "не защищает") == []


# ── review:fp 3 — a relative clause is a clause of its own ─────────────────────────────────────────────────────────
def test_the_main_verb_skips_a_relative_clause():
    flags = _flags("Конь f6, который нападает на e4, сам защищён пешкой g7. "
                   "Пешка e4, которую атакует конь f6, ничем не защищена. "
                   "Пешка e4, на которую нападает конь f6, ничем не защищена. "
                   "Конь f3, который атакует e5, защищён ферзём d1 и пешкой g2. "
                   "The knight on f6, which attacks the pawn on e4, is defended by the pawn on g7.", TWO_KNIGHTS, question="Что тут?")
    assert all(v == [] for _, v in flags), flags
    flags = _flags("Конь f6, который нападает на e4, защищён пешкой d7. "
                   "Пешка e4, которую атакует конь f6, защищена ферзём d1.", TWO_KNIGHTS, question="Что тут?")
    assert "pawn on d7 does not defend Black's knight on f6" in _of(flags, "пешкой d7")[0]
    assert "queen on d1 does not defend White's pawn on e4" in _of(flags, "ферзём d1")[0]


# ── review:fp 4 — «X идёт на sq, и под ударом оказывается Y» ───────────────────────────────────────────────────────
def test_the_inverted_passive_names_its_object_after_the_cue():
    flags = _flags("Конь f3 прыгает на g5, и под ударом оказывается пешка f7. Конь идёт на g5, и под боем уже f7.",
                   TWO_KNIGHTS, question="Что тут?")
    assert all(v == [] for _, v in flags), flags
    flags = _flags("Конь b5 прыгает на c7 с шахом, и под ударом окажутся король e8 и ладья a8.",
                   "r3k3/8/8/1N6/8/8/8/4K3 w - - 0 1", question="Есть ли тут вилка?")
    assert flags[0][1] == []
    flags = _flags("Конь f3 прыгает на g5, и под ударом оказывается пешка e5.", TWO_KNIGHTS, question="Что тут?")
    assert "after 4.Ng5: nothing attacks Black's pawn on e5" in flags[0][1][0]


# ── review:fp 5 and 6 — a placed piece; an ambiguous move reads every way, never as the other side's idea ─────────────
def test_a_piece_placed_on_a_square_is_a_move_there():
    flags = _flags("На b5 конь нападает на d6 и c7. Конь на b5 атакует d6 и c7. On f5 the knight attacks g7 and d6.",
                   SICILIAN, question="Куда пойти конём?")
    assert all(v == [] for _, v in flags), flags
    flags = _flags("На b5 конь нападает на e7.", SICILIAN, question="Куда пойти конём?")
    assert "after 6.N" in flags[0][1][0] and "not e7" in flags[0][1][0]


def test_an_ambiguous_word_move_is_each_reading():
    fen = "8/8/4N3/kn1N2q1/1R6/8/1P3r2/7K w - - 0 1"
    flags = _flags("Конь e6 идёт на c7 и нападает на коня b5. Конь d5 идёт на c7 и нападает на коня b5.", fen, question="Что тут?")
    assert all(v == [] for _, v in flags), flags
    flags = _flags("Конь идёт на c7 и нападает на ферзя g5.", fen, question="Что тут?")
    assert "not Black's queen on g5" in flags[0][1][0] and "idea" not in flags[0][1][0]
    board = chess.Board(SICILIAN)
    assert len(claim_scene.move_readings(board, claim_grammar._move_ref(claim_grammar.Tok("MOVE", 0, 0, "", san="@N:b5")))) == 2


# ── review:fp 7 — the usual puzzle prompts ask for a move ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("q", ["Белые начинают и выигрывают.", "Найди двойной удар.", "What is the winning move?",
                               "Find the tactic.", "Мат в два хода", "Where should my knight go?"])
def test_puzzle_prompts_ask_for_a_move(q):
    assert acr.asks_for_a_move(q)
    fen = "3Rn1k1/1b3ppp/p1p5/4q3/2B1n3/P6P/2Q2PP1/6K1 w - - 0 1"
    ctx = CheckContext.from_fens([fen], question=q)
    acr.add_solution_line(ctx, acr.engine_solution_line({"fen": fen, "lines": [{"moves": ["f4", "Qe7", "Qxe4"]}]}, ctx, q))
    assert ctx.solution_lines == [["f4", "Qe7", "Qxe4"]]


@pytest.mark.parametrize("q", ["Что тут?", "Объясни позицию", "Почему этот ход плохой?", "Найди слабые поля"])
def test_other_questions_do_not(q):
    assert not acr.asks_for_a_move(q)


# ── review:miss F1 — no solution known: the answer's named moves and the forcing moves, not every move ───────────────
def test_a_move_question_does_not_rescue_every_claim():
    text = "Слон c5 под ударом. Пешка f2 связана слоном c5. Какая фигура белых защищает пешку e4?"
    for q in ("Что скажешь о позиции?", "Какой здесь лучший ход?"):
        flags = _flags(text, IT, question=q)
        assert all(v for _, v in flags), (q, flags)


def test_a_puzzle_answer_about_its_unnamed_forcing_move_stays_unflagged():
    # true after 1.Nf7+ (a check), the unnamed first move of the answer
    fen = "r1bq1rk1/ppp2ppp/2n5/3np1N1/2B5/8/PPPP1PPP/RNBQK2R w KQ - 0 7"
    flags = _flags("Конь f7 нападает на ферзя d8.", fen, question="Какой здесь лучший ход?")
    assert flags[0][1] == [] or "f7" not in flags[0][1][0]


# ── review:miss F2 — an absent piece is the error of a present claim ──────────────────────────────────────────────
def test_an_absent_piece_one_move_away_is_not_a_present_fact():
    flags = _flags("Слон c4 защищён пешкой d3. Пешку e4 защищает конь c3. Слона c5 защищает пешка d6.", IT, game=IT_GAME,
                   question="Bc5")
    assert all(v for _, v in flags), flags
    flags = _flags("Конь f6 атакует пешку e4. Конь f6 нападает на пешку g4.", ST4, game=["d4", "Nf6"], question="d4")
    assert all(v for _, v in flags), flags
    # an aim, a chase, a threat may place the piece where its move puts it
    flags = _flags("Слон на g7 целится в c3.", "rnbqkb1r/pp2pp1p/3p1np1/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 0 6", question="x")
    assert flags[0][1] == []


# ── review:miss F3 — only «прикрывать» is to shield ───────────────────────────────────────────────────────────────
def test_shielding_counts_only_for_cover_verbs():
    ruy = "r1bqkbnr/1ppp1ppp/p1n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4"
    flags = _flags("Конь c6 защищает пешку d7. Конь c6 поддерживает пешку d7.", ruy, game="e4 e5 Nf3 Nc6 Bb5 a6".split(), question="a6")
    assert all(v for _, v in flags), flags
    flags = _flags("Пешка e6 прикрывает поле f7 от слона c4.", "rnbqkbnr/pppp1ppp/4p3/8/2B1P3/8/PPPP1PPP/RNBQK1NR b KQkq - 1 2", question="x")
    assert flags[0][1] == []


# ── review:miss F4 — adjectives before the object ─────────────────────────────────────────────────────────────────
def test_an_adjective_before_the_object_keeps_the_claim():
    flags = _flags("Конь f6 атакует слабую пешку d4. Конь f6 напал на центральную пешку d4.", ST4, game=["d4", "Nf6"], question="d4")
    assert all(v for _, v in flags), flags
    flags = _flags("Пешка d4 атакует незащищённую пешку e5.", "rnbqkbnr/pppp1ppp/8/4p3/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 2", question="x")
    assert flags[0][1] == []


# ── review:miss F5 — counts ───────────────────────────────────────────────────────────────────────────────────────
def test_counts_of_attackers_and_defenders():
    flags = _flags("Пешка e5 атакована дважды. Пешку e5 атакуют две белые фигуры. Конь c6 защищён трижды.", IT, question="x")
    assert all(v for _, v in flags), flags
    flags = _flags("Пешка f7 атакована один раз. Конь c6 защищён дважды. Пешка e5 защищена один раз.", IT, question="x")
    assert all(v == [] for _, v in flags), flags


# ── review:miss F6 — a side with the piece in the instrumental; «ходом X» ───────────────────────────────────────────
def test_the_instrument_and_the_move_by_which():
    flags = _flags("Белые защищают пешку e4 конём f3. Ходом d4 ты отгоняешь коня c6. Своим ходом Bc5 чёрные защитили пешку e5.",
                   IT, game=IT_GAME, question="Bc5")
    assert all(v for _, v in flags), flags
    flags = _flags("Чёрные защищают пешку e5 конём c6. Ходом d4 ты атакуешь пешку e5. Белые защищают пешку e4 вместе с конём f3.",
                   IT, game=IT_GAME, question="Bc5")
    assert all(v == [] for _, v in flags), flags


# ── review:miss F7 — a written move's piece is an antecedent; «сыграл» cues a pawn move; «его на f6» ─────────────────
def test_a_written_move_is_an_antecedent():
    flags = _flags("Чёрные сыграли Nf6. Он нападает на твою пешку d4.", ST4, game=["d4", "Nf6"], question="d4", student=chess.WHITE)
    assert _of(flags, "Он нападает")
    flags = _flags("Чёрные сыграли Nf6. Он нападает на поле e4.", ST4, game=["d4", "Nf6"], question="d4", student=chess.WHITE)
    assert _of(flags, "Он нападает") == []
    ruy = "r1bqkbnr/1ppp1ppp/p1n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4"
    flags = _flags("Соперник сыграл a6 и напал на коня f3.", ruy, game="e4 e5 Nf3 Nc6 Bb5 a6".split(), question="a6")
    assert flags[0][1]
    flags = _flags("Соперник сыграл a6 и напал на слона b5.", ruy, game="e4 e5 Nf3 Nc6 Bb5 a6".split(), question="a6")
    assert flags[0][1] == []
    flags = _flags("Его на f6 никто не защищает.", ST4, game=["d4", "Nf6"], question="d4")
    assert flags[0][1]


# ── review:miss F8 — a pawn move advised in words is a line for «Тогда …» ──────────────────────────────────────────
def test_an_advised_pawn_move_is_the_line_of_then():
    flags = _flags("Сыграй d3. Тогда пешка d3 защищает коня f3.", IT, game=IT_GAME, question="Bc5")
    assert _of(flags, "Тогда")
    flags = _flags("Лучший ход — d3. После этого пешка d3 защищает пешку e4.", IT, game=IT_GAME, question="Bc5")
    assert _of(flags, "После этого") == []


# ── review:miss F9 — the geometry of a future square ─────────────────────────────────────────────────────────────
def test_future_geometry_is_judged_as_a_plan():
    flags = _flags("Слон на b2 будет давить на h7. Конь на f5 будет атаковать e6. "
                   "План: поставить коня на e5, откуда он будет бить по e7.", ST4, question="x")
    assert all(v for _, v in flags), flags
    flags = _flags("Слон на b2 будет давить на h8. Конь на f5 будет атаковать e7. Конь f3 будет атаковать e5 после d4.",
                   ST4, question="x")
    assert all(v == [] for _, v in flags), flags


# ── review:miss F10 — the vocabulary by stems ────────────────────────────────────────────────────────────────────
def test_relation_words_by_stem():
    flags = _flags("Ты сыграл Bc4, атаковав пешку e5. Пешку e4 стережёт конь f3. Пешка h7 висит. "
                   "Конь f3 метит в пешку d7.", IT, game=IT_GAME, question="Bc5")
    assert all(v for _, v in flags), flags
    flags = _flags("Пешка e5 висит. Конь f3 метит в пешку e5. Пешка f7 не висит. Пешки c5 и d5 — висячие.",
                   IT, game=IT_GAME, question="Bc5")
    assert all(v == [] for _, v in flags), flags
    # «атаку» is the noun: «развивают атаку на короля» claims nothing
    flags = _flags("Ферзь и ладья чёрных сразу развивают атаку на короля.", "6k1/6p1/2q1p1P1/4Pn1Q/8/5RB1/7K/2r5 b - - 0 1", question="x")
    assert flags[0][1] == []


# ── review:miss F11 — the elided object, the passive agent ───────────────────────────────────────────────────────
def test_an_elided_object_goes_on_from_the_clause_before():
    fen = "rnbqk2r/ppp1bppp/3p4/8/2Bpn3/2P2N2/PP3PPP/RNBQ1RK1 w kq - 0 7"
    game = "e4 e5 d4 d6 c3 Be7 Nf3 Nf6 Bc4 exd4 O-O Nxe4".split()
    flags = _flags("Пешка d4 атакована пешкой c3, но защищена конём e4. Пешку d4 атакует пешка c3, а защищает конь e4.",
                   fen, game=game, question="0-0")
    assert all(v for _, v in flags), flags
    # a subject of its own after «но/а» is no ellipsis
    flags = _flags("Твоя пешка d3 атакует пешку c4, но та теперь защищена слоном.",
                   "r2qkbnr/ppp2ppp/2n1b3/4p3/2p1P3/3P1N2/PPP2PPP/RNBQ1RK1 w kq - 1 6", question="x")
    assert flags[0][1] == []
    flags = _flags("Слон на c4 смотрит на f7, но этот пункт прикрыт пешкой e6.",
                   "r1bqkb1r/pp3pp1/2nppn1p/2p5/2B1P3/3P1N1P/PPP2PP1/RNBQ1RK1 w kq - 1 7", question="Опиши позицию")
    assert flags[0][1] == []
    flags = _flags("Слон b3 атакован пешкой e6.", "r4rk1/pbq2ppp/1p2pn2/n1p5/3P4/PBP1P1N1/1B3PPP/2RQ1RK1 b q - 0 1", question="x")
    assert "pawn on e6 attacks d5 and f5" in flags[0][1][0]


# ── review:miss F12 — «which» presuppositions of more forms; an open «кто?» stays open ───────────────────────────────
def test_which_presuppositions():
    flags = _flags("Чем белые защищают пешку e4? Какая из белых фигур прикрывает пешку e4?", IT, question="x")
    assert all(v for _, v in flags), flags
    flags = _flags("Чем чёрные защищают пешку e5? Кто защищает слона c4? Кто атакует пешку a7?", IT, question="x")
    assert all(v == [] for _, v in flags), flags


# ── review:miss F13, F14 — only-move phrasings; a back-rank king with an air hole ───────────────────────────────────
def test_only_move_phrasings():
    fen = "4k3/8/8/8/8/8/8/4R1K1 b - - 0 1"
    flags = _flags("Король может пойти только на f8. Единственная защита от шаха — Kf8. Есть только один легальный ход: Kf8.",
                   fen, question="Чем чёрным уйти от шаха?")
    assert all(v for _, v in flags), flags
    flags = _flags("Король может пойти только на d8.", "3k4/8/3K4/8/8/8/8/R7 b - - 0 1", question="x")
    assert flags[0][1] == []


def test_no_way_out_for_the_king_not_to_move():
    flags = _flags("У чёрного короля нет выхода.", "6k1/5pp1/7p/8/8/8/8/R5K1 w - - 0 1", question="Как белым поставить мат?")
    assert "h7" in flags[0][1][0]
    flags = _flags("У чёрного короля нет выхода.", "6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1", question="Как белым поставить мат?")
    assert flags[0][1] == []


# ── review:miss F15 — a move number off by one ──────────────────────────────────────────────────────────────────
def test_a_move_number_off_by_one_is_read_on_the_board():
    flags = _flags("После 3.Bg5 слон нападает на пешку e7.", ST4, game=["d4", "Nf6"], question="d4")
    assert flags[0][1]
    # …but never before the line the answer told: «4...d5» after «3...Nf6 4.Ng5» is that line's
    flags = _flags("После 3...Nf6 4.Ng5 конь g5 вместе со слоном c4 атакует f7. Лучший ответ — 4...d5: пешка перекрывает "
                   "диагональ слона. После 5.exd5 твой конь f6 нападает на пешку d5.",
                   "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3", question="Что если я сыграю Nf6?")
    assert _of(flags, "5.exd5") == []


# ── review:miss F16 — «твой» names the student's piece ──────────────────────────────────────────────────────────
def test_the_owner_word_is_checked():
    flags = _flags("Твой слон c5 бьёт по f2.", IT, game=IT_GAME, question="Bc5", student=chess.WHITE)
    assert "Black's, not yours" in flags[0][1][0]
    flags = _flags("Твой слон c4 бьёт по f7. Их слон c5 бьёт по f2.", IT, game=IT_GAME, question="Bc5", student=chess.WHITE)
    assert all(v == [] for _, v in flags), flags


# ── review:wiring 3 — a line written without move numbers ────────────────────────────────────────────────────────
def test_an_unnumbered_opening_line_keeps_its_pawn_moves():
    start = chess.STARTING_FEN
    flags = _flags("После e4 e5 Nf3 конь f3 нападает на пешку e5. После e4 e5 Nf3 Nc6 конь f3 нападает на пешку e5. "
                   "После e4 e6 d4 d5 Nc3 конь c3 давит на пешку d5. После d4 d5 Nf3 Nf6 c4 пешка c4 атакует пешку d5.",
                   start, question="Объясни дебют")
    assert all(v == [] for _, v in flags), flags
    flags = _flags("После e4 e5 Nf3 конь f3 нападает на пешку d5. После Nf3 Nc6 e5 под ударом.", start, question="Объясни дебют")
    assert flags[0][1] and flags[1][1] == []


# ── the hold of a square through the pawn that steps onto it ─────────────────────────────────────────────────────
def test_a_rook_behind_the_pawn_holds_its_promotion_square():
    fen = "8/1P4k1/8/8/8/8/6K1/1r5R w - - 0 1"
    assert _flags("Поле b8 держит ладья b1.", fen, question="x")[0][1] == []
    assert _flags("Поле b8 держит ладья h1.", fen, question="x")[0][1]


# ── review:wiring 1 — the lesson tutor is never checked; a game comment is recorded, not cut ────────────────────────
def test_the_surface_caps_the_mode(monkeypatch):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    ctx = CheckContext.from_fens([TWO_KNIGHTS])
    assert acr.mode(ctx) == "on"
    ctx.relation_surface = "lesson"
    assert acr.mode(ctx) == "off"
    check_sentence("Конь f6 защищает пешку e5 и пешку a7.", ctx)
    assert not ctx.relation_stats.get("calls") and not ctx.relation_shadow
    ctx = CheckContext.from_fens([TWO_KNIGHTS])
    ctx.relation_surface = "game"
    assert acr.mode(ctx) == "shadow"
    issues = check_sentence("Конь f6 защищает пешку a7.", ctx)
    assert not [i for i in issues if i.startswith("on the board now")] and ctx.relation_shadow


def test_the_lesson_tutor_answer_is_the_same_in_every_mode(monkeypatch):
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from src import server

    fen = "r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"
    answer = "Здесь белые развили слона. Пешку e5 защищает только ферзь. Поэтому чёрным стоит подумать о защите."

    def fake_stream(model, system_prompt, msg, history, usage_out):
        for i in range(0, len(answer), 9):
            yield answer[i:i + 9]

    async def no_limit(*a, **k):
        return None

    shown = {}
    client = TestClient(server.app)
    for mode in ("off", "on"):
        monkeypatch.setattr(config, "COACH_RELATION_CHECK", mode)
        with patch("src.server._lesson_chat_stream", side_effect=fake_stream), \
                patch("src.server._lesson_board_facts", return_value={"block": "", "after_fens": [], "note": None}), \
                patch("src.server.enforce_rate_limit", side_effect=no_limit):
            r = client.post("/api/lesson/chat", headers={"X-User-Id": "u"},
                            json={"message": "Что тут происходит?", "lesson_title": "Испанская партия",
                                  "puzzle_context": {"mode": "single", "current_board_fen": fen}})
        shown[mode] = "".join(json.loads(line[6:]).get("delta", "") for line in r.text.splitlines() if line.startswith("data: "))
    assert shown["on"] == shown["off"] == answer


# ── review:wiring 2 — a spoken sentence stays the antecedent even when it was flagged ──────────────────────────────
def test_a_spoken_flagged_sentence_still_names_the_antecedent(monkeypatch):
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    ctx = CheckContext.from_fens([ST4], question="Объясни позицию")
    for s in ("Конь b1 ещё не развит.", "Слон c1 нападает на пешку e5."):
        check_sentence(s, ctx, spoken=True)
    assert check_sentence("Он защищён ферзём d1.", ctx) == []  # «он» is the bishop c1 the listener heard last
    ctx = CheckContext.from_fens([ST4], question="Объясни позицию")
    check_sentence("Конь b1 ещё не развит.", ctx)
    check_sentence("Слон c1 нападает на пешку e5.", ctx)  # cut in text: never shown, names nothing
    assert any("knight on b1" in i for i in check_sentence("Он защищён ферзём d1.", ctx))


# ── review:wiring 4 — off is the whole rollback, the retreat text included ────────────────────────────────────────
def test_off_restores_the_old_retreat_text(monkeypatch):
    from src.answer_check_rules import _retreat_square_issues

    fen = "r2qk2r/ppp2ppp/2np1n2/4p3/2b1P3/2N2N2/PPP2PPP/R1BQK2R w KQkq - 0 8"
    text = "заметь: прогнать слона с c4 недостаточно — он спокойно отойдёт на a6, b5, d3 или e2 и всё равно будет бить по f1."
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "on")
    on = _retreat_square_issues(text, CheckContext.from_fens([fen], question="Почему я не могу рокироваться?"))
    assert len(on) == 1 and "no retreat to b5, d3, e2" in on[0]
    monkeypatch.setattr(config, "COACH_RELATION_CHECK", "off")
    off = _retreat_square_issues(text, CheckContext.from_fens([fen], question="Почему я не могу рокироваться?"))
    assert len(off) == 1 and "no retreat to b5 " in off[0] and "a6 is a real retreat" in off[0]  # the text of 6eb7b972


# ── review:wiring 6 — no catastrophic backtracking on repeated piece words ─────────────────────────────────────────
def test_repeated_piece_words_are_fast():
    import time

    t = time.perf_counter()
    check_sentence("конь " * 200 + "нападает на e5.", CheckContext.from_fens())
    assert time.perf_counter() - t < 1.0


# ── what the full suite showed after the fixes: geometry shown on the board, «висит», "by the X" ─────────────────────
def test_an_absent_piece_hitting_bare_squares_is_its_geometry():
    italian = "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQK2R b KQkq - 0 5"
    assert _flags("Смотри на доску: конь на d5 бьёт f6, e7, c7, b6, b4, c3 и e3.", italian, question="x")[0][1] == []
    assert _flags("Смотри на доску: конь на d5 бьёт f6 и e6.", italian, question="x")[0][1]  # e6 is off its geometry
    assert _flags("Конь на d5 бьёт пешку c7.", italian, question="x")[0][1]  # a named piece: the error it is
    # placed on this board, its lines as the board blocks them (plan §1.3: the bishop on c5 blocks c7)
    assert _flags("Ферзь с поля c4 нападает на f7 и на c7 одновременно.",
                  "8/2p2ppk/2q4p/p1b1pN2/Pp2P3/1P4P1/2P1QP1P/6K1 w - - 0 1", question="x")[0][1]


def test_hanging_is_loose_or_attacked():
    # loose: nothing defends the pawn d4 after 4.Nxd4 exd4 — «висит» is right though nothing attacks it
    fen = "r1bqkbnr/pppp1ppp/8/4p3/2BnP3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
    assert _flags("Nxd4 — конь забирает коня на d4, и после exd4 пешка d4 висит.", fen, question="x")[0][1] == []
    assert _flags("Ладья на d5 висит в воздухе и толком ничего не делает.",
                  "2r2rk1/2p3p1/pp1p1p2/2nR4/P3P2q/1PQ2P1P/2P2PK1/4R3 w - - 0 1", question="x")[0][1] == []
    assert "defended by Black's rook on h8" in _flags("Пешка h7 висит.", IT, question="x")[0][1][0]


def test_an_english_passive_names_its_agent_with_by():
    fen = "2r2rk1/2p3p1/pp1p1p2/2nR4/P3P2q/1PQ2P1P/2P2PK1/4R3 w - - 0 1"
    assert _flags("The pawn on a4 is not attacked by the queen.", fen, question="x")[0][1] == []
    assert _flags("The pawn on a4 is attacked by the queen.", fen, question="x")[0][1]


# ── what validate.sh showed after the fixes ─────────────────────────────────────────────────────────────────────────
def test_a_numbered_move_the_parser_cannot_read_leaves_the_line_unknown():
    start = chess.STARTING_FEN
    # «1.e4e5» (a voice transcript glues the squares): the line is not the one the parser reads
    assert _flags("После 1.e4e5 2.Nf3 чёрные сыграли f6, защитив пешку e5.", start, question="x")[0][1] == []
    assert _flags("После 1.e4 e5 2.Nf3 чёрные сыграли f6, защитив пешку d5.", start, question="x")[0][1]


def test_after_an_object_first_clause_the_object_is_the_topic():
    fen = "rnbqk2r/ppp1bppp/3p4/8/2Bpn3/2P2N2/PP3PPP/RNBQ1RK1 w kq - 0 7"
    game = "e4 e5 d4 d6 c3 Be7 Nf3 Nf6 Bc4 exd4 O-O Nxe4".split()
    flags = _flags("А ещё твоя пешка f2 — её тоже бьёт конь e4, а защищена только королём.", fen, game=game, question="x",
                   student=chess.WHITE)
    assert flags[0][1] == []
    flags = _flags("Конь e4 атакует пешку c3, но защищён пешкой d6.", fen, game=game, question="x")
    assert "pawn on d6 does not defend Black's knight on e4" in flags[0][1][0]


# ── «бьёт» is «attacks» as well as «takes»: the board without the capture is a reading too ─────────────────────────
QUEEN_F4 = "6k1/p1p2p2/3p4/8/5Q2/8/8/6K1 w - - 0 1"


def test_a_strike_word_reads_the_board_without_the_capture_too():
    flags = _flags("Ферзь бьёт пешку d6 и давит на f7. Ферзь забирает пешку d6 и нападает на пешку c7.", QUEEN_F4,
                   question="Что тут есть?")
    assert all(not v for _, v in flags), flags  # f4 hits f7 now; after Qxd6 the queen hits c7
    flags = _flags("Ферзь бьёт пешку d6 и нападает на пешку a7. Ферзь забирает пешку d6 и нападает на пешку f7.",
                   QUEEN_F4, question="Что тут есть?")
    assert _of(flags, "a7") and _of(flags, "забирает")  # false on both readings / «забирает» is the capture only


# ── an object pronoun after a bare square: the square's piece is a reading too ──────────────────────────────────────
def test_an_object_pronoun_after_a_bare_square_has_two_readings():
    fen = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQkq - 1 5"
    flags = _flags("Нет, ферзь d1 не достаёт до f3 — его защищает пешка g2. "
                   "Ферзь d1 смотрит на d8, а его защищает только король e1.", fen, question="Как развиваться дальше?")
    assert all(not v for _, v in flags), flags
    # the pronoun with one reading is still judged: the knight on f3 is no object of a square here
    flags = _flags("Конь f3 нападает на пешку e5, а его защищает пешка h2.", fen, question="Как развиваться дальше?")
    assert _of(flags, "h2")
