"""Old open items of 09–15.10, re-checked on 30.10 against the production run of 29.10.

  * castling promised after a move — «после b3 рокировка станет возможна» with the bishop on c4 retreating to a6
    and still covering f1 — judged after the opponent's reply; the squares a chased piece «retreats» to are
    checked: on b5, d3, e2 the bishop is simply lost (four answers of 29.10, ru and kk);
  * «длинная рокировка возможна» in the forms the check did not read («O-O-O тоже возможна», «…, она возможна»);
  * the false rule «рокироваться можно, только если ладья не атакована» and markdown emphasis that hid claims
    from every check («Пешка на a2 **не атакована**»);
  * «Это выигрыш?» keeps the student's position on the board (a strict lock), voice and text alike;
  * words of another register or language: «епископ», «королева», «рыцарь», «башня», «queen», «pawns»,
    «immediately», «d-файл» — one table, swapped in place where the gender allows, rewritten otherwise;
  * «К:f7» in the lesson task «Пример 4» is read as Nxf7 (fixed on 15.10; regression test here).
"""

import chess
import pytest

from src.answer_check import (CheckContext, SentenceGate, _to_san, check_sentence, chess_terms,
                              foreign_word_issue, proposed_move)
from src.board_lock import _board_lock_level

# 8.? in the Italian with the black bishop on c4 (the castle-00 / d1-b3 / castle-ru / kk-castle rows of 29.10).
BISHOP_C4 = "r2qk2r/ppp2ppp/2np1n2/4p3/2b1P3/2N2N2/PPP2PPP/R1BQK2R w KQkq - 0 8"
# The castle-long-blocked row of 29.10: c1 and d1 taken.
LONG_BLOCKED = "r1bqk2r/ppp2ppp/2np1n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQK2R w KQkq - 2 6"
# «Пример 4» (course «Продвинутая тактика»), the site's solution Rc1.
EXAMPLE_4 = "3r2k1/2q2p1p/p1nNp1p1/1pQ1P3/8/P7/1P3PPP/4R1K1 w - - 0 1"
# «Эндшпиль — Набор 26»: Kg5 and Kh5 both win.
SET_26 = "8/8/7K/8/8/7k/5P2/8 w - - 0 1"


def _ctx(fen=BISHOP_C4, question="", language=None):
    ctx = CheckContext.from_fens([fen], question=question)
    ctx.language = language
    return ctx


# ── Castling after a move ───────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("question,sentence", [
    ("А если сначала сыграть b3, потом рокировка будет?", "Да, после b3 короткая рокировка станет возможна."),
    ("А если сначала сыграть b3, потом рокировка будет?", "После b3 рокировка станет возможна: слон уйдёт и f1 освободится."),
    ("А если сначала сыграть b3, потом рокировка будет?", "Да, станет возможна."),
    ("Что мне делать с рокировкой?", "Сначала b3 — и ты сможешь рокироваться."),
    ("Can I castle after b3?", "After b3 you will be able to castle."),
])
def test_castling_after_b3_is_not_promised(question, sentence):
    issues = check_sentence(sentence, _ctx(question=question))
    assert len(issues) == 1 and "after b3 the opponent answers Ba6" in issues[0] and "f1 is attacked" in issues[0]


@pytest.mark.unit
def test_castling_after_a_move_that_leaves_the_own_piece_in_the_way():
    # The bishop on f1 still stands between the king and the rook after Nf3.
    fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
    issues = check_sentence("После Nf3 можно будет рокироваться в короткую.", _ctx(fen, "Когда мне рокироваться?"))
    assert issues and "after Nf3 White still cannot castle (O-O)" in issues[0] and "f1" in issues[0]


@pytest.mark.unit
@pytest.mark.parametrize("fen,question,sentence", [
    # The reply is named: then castling is possible, and that is what is said.
    (BISHOP_C4, "А если b3?", "После b3, если чёрные ответят Be6, рокировка станет возможна."),
    (BISHOP_C4, "А если b3?", "После b3 Be6 рокировка станет возможна."),
    (BISHOP_C4, "А если b3?", "После b3 рокировка станет возможна, если слон уйдёт с диагонали."),
    (BISHOP_C4, "А если b3?", "После b3 рокировка не станет возможна сразу."),
    # True: after Be2 the king's way is clear at once.
    ("rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 2", "Когда рокироваться?",
     "После Be2 можно будет рокироваться."),
    # True: the bishop that forbade it is taken.
    ("r2qk2r/ppp2ppp/2np1n2/4p3/2b1P3/1BN2N2/PPP2PPP/R2QK2R w KQkq - 0 8", "А если Bxc4?",
     "После Bxc4 рокировка станет возможна."),
])
def test_castling_after_a_move_true_or_conditional_passes(fen, question, sentence):
    assert check_sentence(sentence, _ctx(fen, question)) == []


# ── The squares a chased piece retreats to ──────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("question,sentence,language", [
    # d1-b3, castle-ru, castle-00, d1-why, kk-castle — production 29.10
    ("А если сначала сыграть b3, потом рокировка будет?",
     "Рокировку это само по себе не включает: после b3 короткая всё ещё невозможна, потому что f1 держит под ударом "
     "тот же слон — он отступит на a6, b5, d3 или e2 и продолжит бить по f1.", "ru"),
    ("Можно мне сейчас рокироваться в короткую?",
     "И прогнать слона одной угрозой не выйдет — отступив на a6, b5, d3 или e2, он всё равно будет держать f1 под боем.", "ru"),
    ("А если 0-0?",
     "И прогнать слона недостаточно: он может уйти на a6, b5, d3 или e2 и всё равно держать f1 под ударом.", "ru"),
    ("Почему я не могу рокироваться?",
     "Заметь: прогнать слона с c4 недостаточно — он спокойно отойдёт на a6, b5, d3 или e2 и всё равно будет бить по f1.", "ru"),
    ("Қазір қысқа рокировка жасай аламын ба?",
     "Пілді қуып кету жеткіліксіз: ол a6, b5, d3, e2-ге шегініп, бәрібір f1-ге төнеді.", "kk"),
    # paraphrases
    ("Почему нельзя рокироваться?", "Отогнать слона тоже не поможет — он отойдёт на b5 или d3 и продолжит держать f1.", "ru"),
    ("Why can't I castle?", "Chasing the bishop is not enough: it can retreat to a6, b5 or e2 and keep covering f1.", None),
])
def test_retreat_to_a_square_where_the_piece_is_lost(question, sentence, language):
    issues = check_sentence(sentence, _ctx(question=question, language=language))
    assert any("the bishop on c4 has no retreat to b5" in i and "simply lost (Nxb5" in i for i in issues), issues
    issue = next(i for i in issues if "the bishop on c4" in i)
    if "b3" in sentence:  # judged after b3: d3 and e2 are lost too (30.10 review: the chasing move decides)
        assert issue.startswith("after b3 ") and "Nxe2" in issue and "cxd3" in issue
    if "a6" in sentence:
        assert "a6 is a real retreat" in issue


@pytest.mark.unit
@pytest.mark.parametrize("fen,sentence", [
    (BISHOP_C4, "Прогнать слона мало — он отступит на a6 и всё равно будет бить по f1."),  # a6 is safe: true
    (BISHOP_C4, "Если слон c4 уйдёт на d5, рокировка станет доступна."),  # the move assumed, not a retreat
    (BISHOP_C4, "Слон может отступить на b5, но там его заберёт конь c3."),  # the loss is said
    (BISHOP_C4, "Прогнать слона можно: если он отступит на b5, то Nxb5 выигрывает фигуру."),
    (BISHOP_C4, "Слон не может отступить на d3 — там его съест пешка."),
    (EXAMPLE_4, "После Qa5 конь уходит на b7, и вся связка принесла тебе материал."),  # a move of a line, not a retreat
])
def test_retreats_that_are_true_or_not_offered_pass(fen, sentence):
    issues = check_sentence(sentence, _ctx(fen, "Что тут?"))
    assert not any("has no retreat" in i for i in issues), issues


# ── «Длинная рокировка возможна» with c1 and d1 taken ───────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Длинная рокировка у тебя есть, она возможна.",
    "O-O-O тоже возможна.",
    "**O-O-O** сейчас доступна.",
    "Да, **длинная рокировка** сейчас доступна.",
])
def test_long_castling_with_c1_d1_taken(sentence):
    issues = check_sentence(sentence, _ctx(LONG_BLOCKED, "Могу ли я рокироваться в длинную?"))
    assert issues and "O-O-O" in issues[0] and "the white bishop on c1, the white queen on d1" in issues[0]


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    # the production answer of 29.10, correct
    "Нет, длинную рокировку сейчас сделать нельзя — между королём и ладьёй стоят слон c1 и ферзь d1.",
    "Хочешь сделать длинную — сначала убери фигуры с c1 и d1.",
    "Длинная рокировка станет возможна, когда уйдут слон c1 и ферзь d1.",
    "Есть ли смысл в длинной рокировке, если король там под атакой?",
])
def test_long_castling_true_sentences_pass(sentence):
    assert check_sentence(sentence, _ctx(LONG_BLOCKED, "Могу ли я рокироваться в длинную?")) == []


# ── The castling rule and the rook; markdown emphasis ───────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("question,sentence", [
    ("Что с рокировкой?", "Рокироваться можно, только если ладья не атакована."),
    ("Что с рокировкой?", "Для рокировки ладья не должна быть атакована."),
    ("Что с рокировкой?", "Рокироваться можно, только если **ладья не атакована**."),
    ("Можно рокироваться, если ладья под боем?", "Нельзя рокироваться, если ладья **под ударом**."),
    ("Что с рокировкой?", "**Рокировка невозможна, если ладья под ударом.**"),
])
def test_the_rook_may_be_attacked_when_castling(question, sentence):
    issues = check_sentence(sentence, _ctx(question=question))
    assert any(i.startswith("castling is allowed when the rook is attacked") for i in issues), issues


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Рокироваться можно, даже если ладья атакована.",
    "Да, можно: важно лишь, чтобы король не был под шахом и не проходил через битые поля; ладья может быть атакована.",
    "Атакованная ладья на a1 — не причина отказываться от длинной рокировки.",
])
def test_the_true_rule_passes(sentence):
    issues = check_sentence(sentence, _ctx("4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1", "Можно рокироваться, если ладья под боем?"))
    assert not any(i.startswith("castling is allowed") for i in issues), issues


@pytest.mark.unit
@pytest.mark.parametrize("sentence,issue", [
    ("Пешка на a2 **не атакована**.", "the pawn on a2 IS attacked — by the bishop on c4"),
    ("**Пешка a2** сейчас не под боем.", "the pawn on a2 IS attacked — by the bishop on c4"),
    ("Никто **не атакует** пешку a2.", "the pawn on a2 IS attacked — by the bishop on c4"),
    ("Слон на c4 **висит**.", "the bishop on c4 is not attacked, so it is not hanging"),
    ("Пешка на e4 **ничем не защищена**.", "the pawn on e4 is defended (by c3), not undefended"),
])
def test_emphasis_does_not_hide_a_claim(sentence, issue):
    assert issue in check_sentence(sentence, _ctx(question="Что тут?"))


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Пешка на e4 **защищена** конём c3.",
    "**Слон c4** держит поле f1, поэтому короткая рокировка сейчас невозможна.",
    "Первый ход — **b3**: пешка нападает на слона.",
])
def test_emphasis_on_true_claims_passes(sentence):
    assert check_sentence(sentence, _ctx(question="Что тут?")) == []


# ── «Это выигрыш?» keeps the position ───────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("message", [
    "Это выигрыш?", "Это ничья?", "Это выигрыш или ничья?", "Как думаешь, это выигрыш?", "Ничья ли это?",
    "Это теоретическая ничья?", "Кто выигрывает?", "Белые выигрывают?", "Чёрные спасутся?",
    "Is this a win?", "Is it a draw?", "Can White win?", "Who is winning here?", "Мұнда ұтыс па?",
])
def test_a_question_about_the_result_locks_the_board(message):
    assert _board_lock_level(message, True, False, SET_26) == (SET_26, True, "asked")


@pytest.mark.unit
@pytest.mark.parametrize("message", [
    "а что такое выигрыш?",  # a concept: an example may go up
    "ферзь против ладьи — это выигрыш?",  # a textbook ending named by its material: its own position
    "Ладья и пешка против ладьи — это ничья?",
    "Кто выигрывает в итальянской партии?",  # an opening
    "Кто выиграл чемпионат мира?",
    "Покажи позицию, где это ничья?",
])
def test_other_result_questions_do_not_lock(message):
    assert _board_lock_level(message, True, False, SET_26)[1] is False


@pytest.mark.unit
def test_voice_result_question_locks_the_board_too():
    """The voice coach's tool calls take the lock from the same rule (src/tool_bridge.py)."""
    from src.intent import read_intent

    assert read_intent("Это выигрыш?", fen=SET_26)["kind"] == "board"
    assert read_intent("ферзь против ладьи — это выигрыш?", fen=SET_26)["kind"] != "board"


# ── The words of the language ───────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("sentence,word,right", [
    # production sentences (prod-run outputs 19.10–29.10)
    ("Конём! e8=Q проигрывает — чёрная королева на g7 просто забирает пешку на e7, и у белых ничего не остаётся.",
     "королева", "ферзь"),
    ("Обрати внимание: мат здесь ставит именно ферзь, а свой король на f6 сторожит поля отступления — queen выгоняет "
     "на край, король закрывает дверь.", "queen", "ферзь"),
    ("Ладья всё равно уходит с линии удара, а у белых нет pawns, чтобы когда-нибудь прорваться к королю.", "pawns", "пешка"),
    ("Нет — взять на проходе можно только immediately, следующим ходом.", "immediately", "сразу"),
    ("Проходная, потому что на её пути к полю d8 у чёрных нет ни пешек на d-файле, ни на соседних c- и e-файлах.",
     "d-файле", "вертикаль"),
    ("Рыцарь d5 при этом под боем, поэтому тянуть нельзя: сначала нужно забрать ладью c8.", "Рыцарь", "конь"),
    ("Здесь важна opposition королей.", "opposition", "оппозиция"),
    ("Епископ на c4 сильный.", "Епископ", "слон"),
    ("Это эндгейм с лишней пешкой.", "эндгейм", "эндшпиль"),
])
def test_a_word_of_another_register_or_language(sentence, word, right):
    issue = foreign_word_issue(sentence, "ru")
    assert issue == f"«{word}» is not the Russian chess word: say {right}"
    assert foreign_word_issue(sentence, "en") is None


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Это дебют королевской пешки, и белые сразу занимают центр.",
    "Дебют называется Queen's Gambit — по-русски ферзевый гамбит, и это классика.",
    "Ферзь — самая сильная фигура, в народе его иногда зовут королевой.",
    "Сериал «Ход королевы» как раз про эту девушку и её путь к титулу.",
    "Хочешь, пройди урок целиком по ссылке: chesster.io/learn/chess-basics/the-king-move-right?",
    "Это оппозиция (opposition): короли стоят друг против друга через одно поле.",
    "Чёрные укрепляют пешечную структуру и готовят вывод коня на f6.",
])
def test_russian_words_names_glosses_and_links_pass(sentence):
    assert foreign_word_issue(sentence, "ru") is None


@pytest.mark.unit
def test_the_students_own_word_may_be_explained():
    assert foreign_word_issue("Королева — это ферзь, самая сильная фигура на доске.", "ru",
                              "А как ходит королева?") is None


@pytest.mark.unit
def test_kazakh_words():
    assert foreign_word_issue("Тура d1-ден d8-ге барады, қаралардың патшасы g8-де қамалып қалады.", "kk") is None
    assert foreign_word_issue("Королева қазір d8-де тұр, ол патшаны қорғап тұр.", "kk") == \
        "«Королева» is not the Kazakh chess word: say уәзір"


@pytest.mark.unit
def test_same_gender_words_are_swapped_in_place():
    assert chess_terms("Рыцарь на f3 и башня h1; рыцарем в эндгейме, башней по вертикали.", "ru") == \
        "Конь на f3 и ладья h1; конём в эндшпиле, ладьёй по вертикали."
    assert chess_terms("Королева на d8.", "ru") == "Королева на d8."  # another gender: rewritten instead
    assert chess_terms("Тура мен башня.", "kk") == "Тура мен башня."  # Kazakh: тура is the rook
    assert chess_terms("У белых епископ и конь.") == "У белых слон и конь."  # as before (prod 09.10)


@pytest.mark.unit
def test_the_text_coach_swaps_before_the_check_and_the_voice_coach_is_told():
    ctx = _ctx(chess.STARTING_FEN, "Что делать?", "ru")
    out = SentenceGate(ctx, release_starts=False).feed("Рыцарь на g1 пока не развит, и это стоит исправить. ")
    assert out == [("Конь на g1 пока не развит, и это стоит исправить. ", [],
                    "Конь на g1 пока не развит, и это стоит исправить. ")]
    # The voice check gets the spoken sentence as it is: no swap there, the coach says it again.
    assert check_sentence("Рыцарь на g1 пока не развит, и это стоит исправить.", _ctx(chess.STARTING_FEN, "Что делать?", "ru")) \
        == ["«Рыцарь» is not the Russian chess word: say конь"]


# ── Lesson tasks: Russian capture notation ──────────────────────────────────

@pytest.mark.unit
def test_russian_capture_notation_is_a_move():
    converted, _ = _to_san("Первый ход — **К:f7**: конь берёт пешку f7.")
    assert "Nxf7" in converted
    found = proposed_move("Первый ход — **К:f7**: конь берёт пешку f7.", _ctx(EXAMPLE_4, "Какой здесь первый ход?"))
    assert found is not None and found[2] == "Nxf7"  # the engine stage verifies it as the coach's move


# ── Review of 30.10: false cuts of the checks above ─────────────────────────

ALEKHINE = "rnbqkb1r/pppppppp/5n2/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 1 2"  # 1.e4 Nf6
NIMZO_D4 = "r1bqkbnr/pppppppp/2n5/8/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 1 2"  # 1.d4 Nc6
OPEN_E5 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
TWO_KNIGHTS = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
BISHOP_D6 = "rnbqk2r/ppp2ppp/3B1n2/4p3/4P3/8/PPPP1PPP/RN1QKBNR w KQkq - 0 1"
KING_E7 = "r1bq1bnr/ppppkppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQ - 2 3"


@pytest.mark.unit
@pytest.mark.parametrize("fen,question,sentence,language", [
    # the retreat is judged after the chasing move: 2.e5 Nd5 is the Alekhine, 2.d5 Ne5 a main line
    (ALEKHINE, "Что будет, если я сыграю e5?", "Ход e5 прогоняет коня — он отступит на d5 или g8, это защита Алехина.", "ru"),
    (ALEKHINE, "Что будет, если я сыграю e5?", "Если сыграешь e5, конь отступит на d5 — и это нормальная позиция для чёрных.", "ru"),
    (ALEKHINE, "Что будет, если я сыграю e5?", "После e5 конь отступит на d5, а потом ты атакуешь его ходом c4.", "ru"),
    (ALEKHINE, "Что будет, если я сыграю e5?", "Ответ на e5 простой: конь отступит на d5 и встанет в центре.", "ru"),
    (ALEKHINE, "Что будет, если я сыграю e5?", "При e5 конь отступит на d5, и чёрные получат хорошую игру.", "ru"),
    (ALEKHINE, "What if I play e5?", "If you play e5, the knight will retreat to d5 — that is Alekhine's Defence.", "en"),
    (NIMZO_D4, "А если d5?", "Ход d5 прогоняет коня, и он уйдёт на e5 или b8.", "ru"),
])
def test_a_retreat_is_judged_after_the_chasing_move(fen, question, sentence, language):
    assert check_sentence(sentence, _ctx(fen, question, language)) == []


@pytest.mark.unit
def test_a_retreat_without_a_named_chase_is_judged_after_every_chase():
    # b5 is lost after every move that attacks the bishop (Nc3 covers it); d3 and e2 not after Qd3 / Qe2
    issues = check_sentence("Прогнать слона не выйдет — он отступит на a6, b5, d3 или e2 и всё равно будет бить f1.",
                            _ctx(BISHOP_C4, "Как мне рокироваться?"))
    assert issues == ["the bishop on c4 has no retreat to b5 — there it is simply lost (Nxb5); a6 is a real retreat"]


@pytest.mark.unit
@pytest.mark.parametrize("fen,question,sentence", [
    (OPEN_E5, "Когда я смогу рокироваться?", "После Nf3 ты сможешь рокироваться, но сначала нужно вывести слона f1."),
    (OPEN_E5, "Когда я смогу рокироваться?", "После Nf3 сможешь рокироваться через пару ходов — осталось вывести слона."),
    (OPEN_E5, "Когда я смогу рокироваться?", "После Nf3 и вывода слона ты сможешь рокироваться."),
    (BISHOP_C4, "Как мне рокироваться?", "После b3 рокировка станет возможна лишь тогда, когда слон уйдёт с диагонали a6–f1."),
    (TWO_KNIGHTS, "Если я сыграю h3, смогу потом рокироваться?", "Да, будет возможна после того, как уберёшь слона с f1."),
    (TWO_KNIGHTS, "Если я сыграю h3, рокировка станет возможна?", "Да, станет возможна, но сначала убери слона с f1."),
    # the opponent's castling after the student's move: Bxe5 takes the bishop off f8's diagonal
    (BISHOP_D6, "Почему чёрные не рокируются?", "После Bxe5 у чёрных рокировка станет возможна."),
    (BISHOP_D6, "Почему чёрные не рокируются?", "После Bxe5 чёрным короткая рокировка станет доступна."),
])
def test_castling_after_a_move_with_a_later_condition_or_the_other_side_passes(fen, question, sentence):
    ctx = _ctx(fen, question)
    ctx.student_color = chess.WHITE
    assert check_sentence(sentence, ctx) == []


@pytest.mark.unit
def test_the_opponents_castling_after_a_move_is_judged_for_the_opponent():
    ctx = _ctx(BISHOP_D6, "Почему чёрные не рокируются?")
    ctx.student_color = chess.WHITE
    issues = check_sentence("После h3 у чёрных рокировка станет возможна.", ctx)
    assert issues and issues[0].startswith("after h3 Black still cannot castle") and "f8 is attacked" in issues[0]


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Рокировка у тебя ещё есть: король и ладьи не ходили, осталось убрать слона с f1.",
    "Право на рокировку у тебя есть, но сейчас рокироваться нельзя: между королём и ладьёй стоит слон f1.",
    "Да, рокировка у тебя сейчас есть как право, но физически сделать её мешают слон и конь.",
])
def test_the_right_to_castle_is_not_castling_now(sentence):
    assert check_sentence(sentence, _ctx(TWO_KNIGHTS, "Я ещё могу рокироваться?", "ru")) == []


@pytest.mark.unit
def test_the_right_to_castle_is_gone_when_the_king_has_moved():
    assert check_sentence("Рокировка у чёрных ещё есть.", _ctx(KING_E7, "Могут ли чёрные рокироваться?", "ru")) == \
        ["Black has no right to castle any more: the king has left e8"]


@pytest.mark.unit
@pytest.mark.parametrize("sentence,language", [
    ("Оппозиция, по-английски opposition, — это когда короли стоят друг напротив друга через одно поле.", "ru"),
    ("Эндшпиль по-английски называется endgame, а по-русски это заключительная стадия партии.", "ru"),
    ("По-английски ферзь называется queen, а слон — bishop.", "ru"),
    ("Цугцванг — немецкое слово zugzwang, означает «принуждение к ходу».", "ru"),
    ("Фианкетто — от итальянского fianchetto, это развитие слона на большую диагональ.", "ru"),
    ("Взятие на проходе по-английски называется en passant, это французское выражение.", "ru"),
    ("Лучшая книга по эндшпилю для тебя — Silman's Complete Endgame Course, она идёт по уровням.", "ru"),
    ("Для сильных игроков есть Dvoretsky's Endgame Manual, но это уже серьёзный учебник по эндшпилю.", "ru"),
    ("Это защита двух коней, по-английски Two Knights Defense.", "ru"),
    ("Хорошая книга про пешечную структуру — Pawn Structure Chess Сольтиса.", "ru"),
    ("Начни с курса на Lichess под названием King and Pawn Endgames, он бесплатный.", "ru"),
    ("Шанышқы ағылшынша fork деп аталады, ал ферзь queen деп аталады.", "kk"),
    ("Посмотри сериал Ход королевы — там хорошо показан мир шахматных турниров.", "ru"),
    ("Можно открыть файл PGN с партией через кнопку загрузки на сайте.", "ru"),
])
def test_a_word_named_as_a_word_or_a_title_passes(sentence, language):
    assert foreign_word_issue(sentence, language, "Что почитать?") is None


@pytest.mark.unit
def test_the_students_word_in_another_form_and_english_far_from_the_right_word():
    assert foreign_word_issue("Это одна и та же фигура: королевой её называют только в быту.", "ru",
                              "Кто сильнее ферзь или королева?") is None
    assert foreign_word_issue("Займи открытый файл ладьёй, это главный план.", "ru") == \
        "«открытый файл» is not the Russian chess word: say вертикаль"
    # the right word far away is not a gloss (prod 29.10)
    assert foreign_word_issue("Обрати внимание: мат здесь ставит именно ферзь, а свой король на f6 сторожит поля "
                              "отступления — queen выгоняет на край, король закрывает дверь.", "ru") == \
        "«queen» is not the Russian chess word: say ферзь"


@pytest.mark.unit
@pytest.mark.parametrize("question,sentence", [
    ("Почему ладью называют башней?", "Ладью часто называют башней из-за её формы. "),
    ("Почему конь — это рыцарь?", "В английском конь называется рыцарем, а по-русски это просто конь. "),
    ("Что такое эндгейм?", "Слово эндгейм — это калька с английского, правильно говорить эндшпиль. "),
])
def test_a_word_the_sentence_explains_is_not_swapped(question, sentence):
    ctx = _ctx(TWO_KNIGHTS, question, "ru")
    gate = SentenceGate(ctx, release_starts=False)
    assert gate.feed(sentence) + gate.flush() == [(sentence, [], sentence)]
    assert chess_terms(sentence, "ru", question) == sentence  # the server's pass over the shown text
    assert chess_terms("Башня на h1 стоит плохо. Ладью называют башней.", "ru") == \
        "Ладья на h1 стоит плохо. Ладью называют башней."


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Есть миф, будто ладья не должна быть атакована при рокировке, но в правилах этого нет.",
    "Нет такого правила, что ладья не должна быть атакована.",
    "Многие думают, что рокироваться можно, только если ладья не атакована, но это не так.",
    "Есть миф, будто ладья не должна быть под боем при рокировке, но в правилах этого нет.",
])
def test_the_false_rook_rule_told_as_a_myth_passes(sentence):
    assert check_sentence(sentence, _ctx(TWO_KNIGHTS, "Можно рокироваться, если ладья под боем?", "ru")) == []
