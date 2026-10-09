"""Broad fixes of 2026-10-08, after the client's «Что если я пойду Се3?».

One test per class of failure seen on production (06–08.10), not per case:
moves written any way, a move already played, fragments of cut sentences,
thinking aloud, arrows standing for moves, short English sentences, a lone FEN
read as English, en passant and defences misjudged, invented game history.
"""

import chess
import pytest

from src.answer_check import CheckContext, SentenceGate, check_sentence, language_issue
from src.board_markup import MarkupFilter
from src.move_matcher import named_moves
from src.prompt_builder import _script_language, question_moves

ALEX = "r1bqk2r/2pn1pp1/2pp4/p1b2P1p/4P3/2NB4/PPP3PP/R1BQ1R1K w kq - 0 1"

# The battery behind the matcher: 48 everyday ways to write four moves of the client's position.
BATTERY = {
    "Be3": ["Се3", "Сe3", "Be3", "С:е3", "Сс1-е3", "Сc1-e3", "с1-е3", "c1e3", "Bc1e3", "С е3", "C e3", "Ce3", "се3",
            "СЕ3", "bishop e3", "слон е3", "слоном на е3", "слон на е3", "слона на e3", "пойду слоном е3",
            "а если слон пойдёт на е3", "поставлю слона на е3", "Слон c1 на e3"],
    "Qxh5": ["Фh5", "Ф:h5", "Фxh5", "ферзём на h5", "ферзь бьёт h5", "возьму пешку h5 ферзём", "Qh5", "взять на h5",
             "съем пешку h5"],
    "Nb5": ["Кb5", "Кв5", "Кб5", "конь b5", "конём на b5", "Nb5", "конь прыгает на b5"],
    "f6": ["f6", "f5-f6", "пешка f6", "пешкой на f6", "а если f6?", "двину пешку f на f6", "ф6"],
}


def _ask(words: str) -> str:
    starts = ("а если", "пойду", "поставлю", "возьму", "съем", "двину", "взять")
    return words + "?" if words.startswith(starts) else f"Что если я пойду {words}?"


@pytest.mark.parametrize("san,words", [(s, w) for s, ws in BATTERY.items() for w in ws])
def test_every_way_of_writing_a_move(san, words):
    assert san in [m["san"] for m in question_moves(_ask(words), ALEX) if m.get("legal")]


@pytest.mark.parametrize("text", [
    "Почему конь f6 висит?", "После 1.e4 e5 что играть?", "Мат в 3 хода здесь есть?", "с 3 фигурами",
    "Пешка e4 под ударом?", "Что делать со слоном d3?", "Слон d3 смотрит на h7.", "Поле e5 слабое?",
])
def test_a_square_or_a_piece_is_not_a_move(text):
    assert named_moves(text, chess.Board(ALEX)) == []


def test_a_move_already_played_is_not_illegal():
    named = question_moves("Я сыграл Qb6. Это мат?", "k7/8/1Q6/8/8/8/8/2K5 b - - 0 1")
    assert named[0]["verdict"].startswith("already played")


def test_a_cut_sentence_leaves_no_fragment():
    gate = SentenceGate(CheckContext.from_fens([ALEX]))
    assert gate.feed("Сначала нужно было поставить чёрную ") == []  # nothing of it goes out before its check


def test_a_self_correction_after_an_ellipsis_is_dropped():
    gate = SentenceGate(CheckContext.from_fens([ALEX]))
    out = gate.feed("Второй вариант — сразу Be3, блокируя... нет, точнее защищая f1. ")
    assert any(o[1] for o in out)


def test_an_arrow_standing_for_the_move_is_written():
    f = MarkupFilter("r2qkb1r/pp2nppp/3p4/2pNN1B1/1BbnP3/3P4/PPP2PPP/R2bK2R w KQkq - 1 1")
    out, _ = f.feed("Ставит мат: [[arrows: b4f8]]. После [[arrows: d5f6]] чёрным остаётся взятие. "
                    "Смотри на доску [[arrows: e5f7]] — тут всё ясно.")
    out += f.flush()
    assert "мат: b4–f8." in out and "После Nf6+ чёрным" in out and "доску — тут" in out


@pytest.mark.parametrize("text,english", [
    ("I'll pull up the game.", True), ("I'll look at the position carefully.", True),
    ("(Fried Liver Attack)", False), ("**DrNykterstein** (Lichess):", False), ("1.e4 e5 2.Nf3 Nc6 3.Bb5", False),
])
def test_a_short_english_sentence_in_a_russian_answer(text, english):
    assert bool(language_issue(text, "ru")) is english


@pytest.mark.parametrize("message,lang", [
    (ALEX, None), ("https://lichess.org/abc12345", None), ("What should I play here?", "en"), ("Что тут? " + ALEX, "ru"),
])
def test_a_fen_or_a_link_carries_no_language(message, lang):
    assert _script_language(message) == lang


def test_en_passant_is_a_capture_of_the_pawn_that_passed():
    ep = "rnbqkbnr/1pp1pppp/p7/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3"
    assert check_sentence("Пешка e5 бьёт пешку d5, которая только что прыгнула через два поля, и встаёт на d6.",
                          CheckContext.from_fens([ep])) == []
    assert check_sentence("Пешка e5 бьёт пешку d5.", CheckContext.from_fens(["rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq - 0 3"]))


def test_a_defence_is_of_ones_own_piece():
    fen = "r1bq1b1r/ppp3pp/2n1k3/3np3/2B5/5Q2/PPPP1PPP/RNB1K2R w KQ - 2 8"
    assert check_sentence("Потому что ферзь d8 и король e6 держат коня, размен вам ничего не даёт.", CheckContext.from_fens([fen])) == []


def test_the_student_who_played_the_move_owns_it():
    ctx = CheckContext.from_fens(["k7/8/1Q6/8/8/8/8/2K5 b - - 0 1"], student_color=chess.WHITE)
    assert check_sentence("У чёрных король на a8, а твой ферзь на b6 отнимает у него все поля.", ctx) == []


def test_invented_game_history():
    fen = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w kq - 6 5"
    s = "Партия шла так: 1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.Nc3? — и вот здесь чёрные успели походить конём на f6."
    assert check_sentence(s, CheckContext.from_fens([fen]))
    assert check_sentence(s, CheckContext.from_fens([fen], ["1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5"])) == []


@pytest.mark.parametrize("sentence,caught", [
    ("Конь с ф3 прыгает на д5.", True),  # transliterated squares in a speech transcript
    ("Самое полезное сейчас — убрать коня с d3, где он стоит неуклюже.", True),  # the bishop stands there
    ("Можно перевести коня с c3 на e2.", False),
])
def test_squares_and_pieces_in_other_spellings(sentence, caught):
    fen = ALEX if "d3" in sentence or "c3" in sentence else "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
    assert bool(check_sentence(sentence, CheckContext.from_fens([fen]))) is caught


# A lesson puzzle with castling rights its kings and rooks no longer allow (16 of the site's 187).
BAD_CASTLING = "r1q1kb1r/pppn1npp/8/4p1B1/8/1Q6/PPP2PPP/RN2R1K1 w Qkq - 0 1"


def test_a_lesson_fen_with_impossible_castling_is_repaired_not_refused():
    from src.fen_repair import repair_fen

    assert repair_fen(BAD_CASTLING) == "r1q1kb1r/pppn1npp/8/4p1B1/8/1Q6/PPP2PPP/RN2R1K1 w kq - 0 1"
    assert repair_fen(chess.STARTING_FEN) == chess.STARTING_FEN  # a valid FEN is left exactly as it is
    assert repair_fen("garbage") == "garbage" and repair_fen(None) is None
    assert repair_fen("4k3/8/8/8/8/8/8/4K3 w - e3 0 1") == "4k3/8/8/8/8/8/8/4K3 w - - 0 1"


def test_the_engine_tools_and_notes_take_such_a_fen():
    import json

    from src.prompt_builder import board_facts_block
    from src.tools import discover_and_register
    from tools.registry import registry

    discover_and_register()
    out = json.loads(registry.dispatch("check_moves", {"fen": BAD_CASTLING, "moves": ["Qe6+"]}))
    assert "error" not in out and out["results"][0]["legal"] is True
    assert board_facts_block(BAD_CASTLING)
    assert [m["san"] for m in question_moves("А если Qe6+?", BAD_CASTLING)] == ["Qe6+"]


@pytest.mark.parametrize("text,flagged", [
    ("第一着是 **Kd4**——把马跳向中心，切断白方后的前路。", True),
    ("مرحبا بك في الشطرنج", True),
    ("Защита Грюнфельда (Grünfeld) и система Рети (Réti) — гипермодерн.", False),
])
def test_a_sentence_in_another_script(text, flagged):
    assert bool(language_issue(text, "ru")) is flagged


@pytest.mark.parametrize("text,fixed", [
    ("Первый ход — **Kxf2** (конь берёт пешку f2 с шахом).", "Первый ход — **Nxf2** (конь берёт пешку f2 с шахом)."),
    ("Итальянская партия — 1.e4 e5 2.Kf3 Kc6 3.Cc4.", "Итальянская партия — 1.e4 e5 2.Nf3 Nc6 3.Bc4."),
    ("Движок даёт линию 1.Kc3 Kb8 2.Qg7 Ka8.", "Движок даёт линию 1.Kc3 Kb8 2.Qg7 Ka8."),  # an endgame line: the king
    ("Король обязан ответить, а после Kxf2 конь f6 прыгает на g4.", "Король обязан ответить, а после Kxf2 конь f6 прыгает на g4."),
])
def test_russian_piece_letters_typed_in_latin(text, fixed):
    from src.answer_check import normalize_notation

    assert normalize_notation(text) == fixed


START4 = "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"


@pytest.mark.parametrize("sentence,caught", [
    ("На b3 пешка пойти не может.", True),
    ("Конь b1 не может пойти на c3.", True),
    ("Слон c4 не может пойти на f7, там пешка под защитой короля.", False),  # a capture that costs, not a rule
    ("Если слон уйдёт, конь не может пойти на d4.", False),
    ("Пешка b2 не может пойти на b5.", False),
])
def test_a_legal_move_denied(sentence, caught):
    assert bool(check_sentence(sentence, CheckContext.from_fens([START4]))) is caught


def test_the_castling_rule_named_in_the_question_only():
    ctx = CheckContext.from_fens(["4k2r/8/8/8/8/8/8/4K2R w K - 0 1"], question="Можно рокироваться, если ладья под боем?")
    assert check_sentence("Можно, если только ваша ладья не находится под боем.", ctx)
    assert check_sentence("Нет, при атакованной ладье рокировка запрещена.", ctx)
    assert check_sentence("Да, можно: даже если ладья под боем, рокировка разрешена.", ctx) == []


def test_a_wrong_no_to_the_castling_rule_question():
    ctx = CheckContext.from_fens([chess.STARTING_FEN], question="Можно ли рокироваться, если моя ладья под боем?")
    assert check_sentence("Нет, нельзя — рокировка через битое поле запрещена.", ctx)
    assert check_sentence("Нет, ладья под боем рокировке не мешает.", ctx) == []


@pytest.mark.parametrize("text,out", [
    ("Затем выводи короля из-под пешки, а ладью поставь на четвёртую.", "Выводи короля из-под пешки, а ладью поставь на четвёртую."),
    ("**Затем** выводи короля из-под пешки.", "Выводи короля из-под пешки."),
    ("Затяни узел потуже.", "Затяни узел потуже."),
])
def test_a_sentence_leaning_on_one_left_out(text, out):
    from src.answer_check import strip_leaning_start

    assert strip_leaning_start(text) == out


@pytest.mark.parametrize("fen,sentence,caught", [
    ("3R1rk1/6pp/3Q4/pp2Pq2/4Nn2/P7/1P6/K7 w - - 0 1", "Первый ход — **...Rxf3!**.", True),  # a lesson diagram's move
    ("3R1rk1/6pp/3Q4/pp2Pq2/4Nn2/P7/1P6/K7 w - - 0 1", "Первый ход — **Nf6+**.", False),
    ("r1b2rk1/ppp2ppp/1bnq1n2/1B1p2B1/3PP3/2N2N2/PP3PPP/R2Q1RK1 w - - 0 1", "Первый ход — **1...Ba6!**", True),
    (chess.STARTING_FEN, "Первый ход — e4: пешка занимает центр.", False),
])
def test_the_announced_first_move_is_a_move_of_the_board(fen, sentence, caught):
    assert bool(check_sentence(sentence, CheckContext.from_fens([fen]))) is caught


def test_the_only_reply_to_a_sacrifice_is_a_fact():
    from src.position_facts import _forced_replies

    board = chess.Board("r1b4k/pp1n2p1/1qp1B1Pp/2p2p2/3P4/2Q1P3/PP1K1PP1/R6R w - - 0 1")
    move = board.parse_san("Rxh6+")
    after = board.copy()
    after.push(move)
    assert _forced_replies(board, move, after) == "after Rxh6+, Black has only one legal move: gxh6 — it must take the rook on h6"


def test_a_pawn_capture_in_the_question_is_read_not_a_crash():
    fen = "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
    assert [m["san"] for m in question_moves("Почему не exd5?", fen) if m.get("legal")] == ["exd5"]
    assert [m["san"] for m in question_moves("А если b3?", fen) if m.get("legal")] == ["b3"]


def test_the_best_line_is_explained_move_by_move():
    from src.position_facts import explain_line

    board = chess.Board("r1b4k/pp1n2p1/1qp1B1Pp/2p2p2/3P4/2Q1P3/PP1K1PP1/R6R w - - 0 1")
    told = explain_line(board, ["h1h6", "g7h6", "d4c5", "d7e5", "c3e5"])
    assert told == ("Rxh6+ (takes the pawn h6, check); gxh6 (the only legal move, takes the rook h6); "
                    "dxc5+ (takes the pawn c5, discovered check by the queen c3); Ne5 (blocks the check); "
                    "Qxe5# (takes the knight e5, mate)")


@pytest.mark.parametrize("sentence,caught", [
    ("Король обязан отойти — и на h8 у него нет покоя.", True),  # after Rxh6+ only gxh6 is legal
    ("Пешка g7 обязана взять ладью.", False),
])
def test_a_forced_reply_is_judged_after_the_move(sentence, caught):
    ctx = CheckContext.from_fens(["r1b4k/pp1n2p1/1qp1B1Pp/2p2p2/3P4/2Q1P3/PP1K1PP1/R6R w - - 0 1"])
    check_sentence("Первый ход — **Rxh6+**.", ctx)
    assert bool(check_sentence(sentence, ctx)) is caught


@pytest.mark.parametrize("fen,question,sentence", [
    # the pawn named by the square it left in this sentence
    ("r1b4k/pp1n2p1/1qp1B1Pp/2p2p2/3P4/2Q1P3/PP1K1PP1/R6R w - - 0 1", "А если я сыграю Bxf5?",
     "Посмотри на чёрный ответ **cxd4**: пешка c5 бьёт твою пешку d4 и одновременно нападает на твоего ферзя c3."),
    # Russian word order: the pawn on b2 holds a3
    ("8/4b1k1/6pp/pp1p4/3PpP1P/PpP3P1/1P1B3K/8 b - - 0 1", "А если я сыграю Bxh4?", "Обе они защищены: a3 держит пешка b2, а h4 — пешка g3."),
])
def test_true_sentences_of_the_lesson_tutor_are_not_cut(fen, question, sentence):
    board = chess.Board(fen)
    named = question_moves(question, fen)
    after = [q["after_fen"] for q in named if q.get("after_fen")]
    assert check_sentence(sentence, CheckContext.from_fens([fen] + after, question=question)) == []


def test_a_mate_the_student_walks_into_is_not_this_boards_mate():
    ctx = CheckContext.from_fens(["2r2b2/5Rpk/5pR1/5P2/6N1/8/3r3P/6K1 w - - 0 1"], question="А если я сыграю Rfxf6?")
    ctx.engine_eval, ctx.engine_mate = 100.0, 3
    assert check_sentence("То есть вместо того, чтобы атаковать, ты сам пропускаешь мат в один ход.", ctx) == []


def test_an_undefended_claim_is_about_the_piece_named():
    ctx = CheckContext.from_fens(["5rk1/q4ppp/2b1pb2/8/r1Bp4/P2Q1N2/R1P2PPP/3R2K1 b - - 0 1"])
    check_sentence("Первый ход — **Rxc4**.", ctx)
    assert check_sentence("Слон на c4 ничем не защищён, а ладья его бьёт.", ctx)


@pytest.mark.parametrize("message", [
    "Разбери мою партию: 1.e4 e5 2.Кf3 Кc6 3.Сc4 Сc5 4.c3 Кf6 5.d4 e:d4 6.c:d4 Сb4+",
    "Разбери мою партию: 1.е4 е5 2.Кф3 Кс6 3.Сс4 Сс5 4.с3 Кф6 5.д4 е:д4 6.с:д4 Сб4+ 7.Кс3 0-0",
])
def test_a_game_in_russian_notation_is_read(message):
    from src.model_router import extract_game_pgn

    pgn = extract_game_pgn(message)
    assert pgn and pgn.startswith("1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5")


def test_a_tool_error_tells_the_model_not_to_invent():
    import json

    from src.tools import ERROR_HINT, discover_and_register
    from tools.registry import registry

    discover_and_register()
    assert json.loads(registry.dispatch("analyze_position", {"fen": "garbage"}))["hint"] == ERROR_HINT


@pytest.mark.parametrize("fen,solution,bad", [
    ("2K5/4p3/1p2k3/1p1R1p2/1P1PP3/1B6/1q6/8 w - - 0 1", ["Rxf5+"], "wrong here"),  # Мат в 3 хода — Набор 27, №1
    ("7k/8/8/8/8/4K3/8/8 w - - 0 1", ["d4e4"], "not a legal move"),  # Король — Ход вправо
    ("r1b1qrn1/pppnbkpp/5p2/n7/2P2BP1/3PQ3/PP2PPBP/RNB1K1NR w KQ - 0 1", ["Qe6+"], "not a legal chess position"),
    ("8/5p1k/6pp/3q4/4N3/7P/5PP1/6K1 w - - 0 1", ["Nf6+"], None),  # a right one
])
def test_the_sites_listed_solution_is_checked(fen, solution, bad):
    from src.hypothetical import site_solution_note

    note = site_solution_note(fen, solution)
    assert (note is None) if bad is None else (bad in note)


def test_a_pronoun_agrees_with_its_piece():
    fen = "r4rk1/ppq2pp1/2n2n1p/3p2N1/3P3N/2P5/P1B2PPP/R2Q1RK1 w - - 0 1"
    ctx = CheckContext.from_fens([fen])
    assert check_sentence("Конь забирает пешку h7 с шахом, и это вилка: он бьёт одновременно короля на f8 и коня на f6.", ctx) == []


def test_a_move_legal_only_on_a_lesson_diagram_is_not_the_answer():
    fen = "6k1/3bpp2/3p2p1/2qP4/1p1Q2P1/pP3P2/P1P1N2r/1K2R3 b - - 0 1"
    ctx = CheckContext.from_fens([fen])
    ctx.add_text('{"lesson_text": "[Диаграмма: 6k1/5ppp/8/8/8/8/5PPq/6K1 b - - 0 1]"}')
    assert check_sentence("Первый ход чёрных — **Qxg2+ (ферзь берёт пешку g2 с шахом)**.", ctx)
    assert check_sentence("Первый ход чёрных — **Rxe2**.", CheckContext.from_fens([fen])) == []


def test_famous_games_are_verified_scores():
    from src.famous_games import GAMES, _replay

    endings = {"opera": "Rd8#", "immortal": "Be7#", "evergreen": "Bxe7#", "game-of-the-century": "Rc2#",
               "kasparov-topalov": "Qa7"}
    for g in GAMES:
        game, _moves = _replay(g)
        assert not game.errors and game.end().san() == endings[g["key"]]


@pytest.mark.parametrize("message,key", [
    ("Покажи на доске оперную партию Морфи и коротко объясни, в чём её красота.", "opera"),
    ("Покажи бессмертную партию Андерсена против Кизерицкого.", "immortal"),
    ("Разбери бессмертную партию Каспарова", "kasparov-topalov"),
    ("Покажи партию века", "game-of-the-century"),
    ("Как играть против защиты Филидора?", None),
])
def test_a_famous_game_named_in_the_message(message, key):
    from src.famous_games import famous_game

    found = famous_game(message)
    assert (found and found["key"]) == key


def test_the_opera_game_told_with_a_reply_that_does_not_exist():
    from src.famous_games import famous_game

    ctx = CheckContext.from_fens([chess.STARTING_FEN], [famous_game("оперная партия")["pgn"]])
    check_sentence("Потом 15.Bxd7+ — снова отдают слона, 16.Qb8+ — отдают ферзя!", ctx)
    assert check_sentence("Чёрные обязаны ответить королём на e7 — брать ферзя нельзя.", ctx)


@pytest.mark.parametrize("fen,question,sentence,caught", [
    (chess.STARTING_FEN, "Можно ли рокироваться, если моя ладья под боем?",
     "Перед рокировкой проверяй поля короля — e1, f1, g1 при короткой и d1, c1, b1 при длинной.", True),
    (chess.STARTING_FEN, "", "При длинной рокировке поле b1 должно быть пустым, но может быть под боем.", False),
    (chess.STARTING_FEN, "", "А если позиция повторилась трижды — ничья объявляется автоматически.", True),
    (chess.STARTING_FEN, "", "После пятикратного повторения ничья наступает автоматически.", False),
    ("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w kq - 6 5", "", "А слон чёрных на c4 уже смотрит на f7.", True),
    ("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w kq - 6 5", "", "Белый слон на c4 смотрит на f7.", False),
    ("r2qk2r/ppp2ppp/2np1n2/4p3/2b1P3/2N2N2/PPP2PPP/R1BQK2R w KQkq - 0 8", "А если 0-0?",
     "А если слон c4 всё-таки уйдёт на a6, он потеряет давление на f1, и рокировка станет доступна.", True),
    ("r2qk2r/ppp2ppp/2np1n2/4p3/2b1P3/2N2N2/PPP2PPP/R1BQK2R w KQkq - 0 8", "А если 0-0?",
     "Если слон c4 уйдёт на d5, рокировка станет доступна.", False),
    (chess.STARTING_FEN, "Покажи на доске оперную партию Морфи и коротко объясни, в чём её красота.",
     "Покажи на доске оперную партию Морфи и коротко объясни, в чём её красота.", True),
])
def test_side_claims_of_the_prod_run(fen, question, sentence, caught):
    assert bool(check_sentence(sentence, CheckContext.from_fens([fen], question=question))) is caught


@pytest.mark.parametrize("sentence,caught", [
    ("После Се3 чёрные просто бьют Сxc5 — и ты теряешь слона за пешку.", True),  # Bxc5 is White's (the client's Се3)
    ("Свою e3-пешку ты ничем не защищаешь.", True),  # a bishop stands on e3
    ("Чёрные просто бьют Bxe3, и слон пропадает.", False),
    ("Белые бьют Bxc5.", False),
])
def test_a_move_given_to_the_wrong_side(sentence, caught):
    named = question_moves("Что если я пойду Се3? Хороший ли это ход?", ALEX)
    ctx = CheckContext.from_fens([ALEX] + [q["after_fen"] for q in named if q.get("after_fen")],
                                 question="Что если я пойду Се3? Хороший ли это ход?")
    assert bool(check_sentence(sentence, ctx)) is caught


@pytest.mark.parametrize("case,sentence,want", [
    (191, "Ход у чёрных — и здесь спасает только один ход: **Ke5!**", "Ke5"),  # loses; Kf5 holds
    (208, "**Kxb3!** — король бьёт слона. Это единственный ход, который спасает партию.", "Kxb3"),  # loses
])
def test_a_move_marked_as_the_only_one_goes_to_the_engine(case, sentence, want):
    import json

    from src.answer_check import proposed_move
    from src.fen_repair import repair_fen

    c = json.load(open("eval/bench/2026-10-06-blind-spots/curriculum_cases.json"))[case] \
        if __import__("os").path.exists("eval/bench/2026-10-06-blind-spots/curriculum_cases.json") else None
    if c is None:
        pytest.skip("bench data is not in the repository")
    found = proposed_move(sentence, CheckContext.from_fens([repair_fen(c["fen"])]))
    assert found and found[2] == want


def test_the_side_to_move_named_for_the_board():
    fen = "r1b2rk1/ppp2ppp/1bnq1n2/1B1p2B1/3PP3/2N2N2/PP3PPP/R2Q1RK1 w - - 0 1"
    assert check_sentence("На доске ход чёрных, и у белых есть защитник.", CheckContext.from_fens([fen]))
    assert check_sentence("На доске ход белых.", CheckContext.from_fens([fen])) == []


def test_the_start_position_does_not_excuse_an_announced_move():
    fen = "r1b2rk1/ppp2ppp/1bnq1n2/1B1p2B1/3PP3/2N2N2/PP3PPP/R2Q1RK1 w - - 0 1"
    assert check_sentence("Первый ход здесь **1.e4** — белые занимают центр.", CheckContext.from_fens([fen]))


def test_an_arrow_after_a_colon_mid_sentence_is_the_move():
    f = MarkupFilter("8/8/8/8/8/2k5/8/K1N1N3 w - - 0 1")
    out, _ = f.feed("Начни с шаха: [[arrows: e1d3]] и попробуй загнать.")
    assert (out + f.flush()) == "Начни с шаха: Ned3 и попробуй загнать."


def test_an_infinitive_recommendation_goes_to_the_engine():
    from src.answer_check import normalize_notation, proposed_move

    fen = "r1bqk2r/1pppbppp/p1n2n2/4p3/B3P3/5N2/PPPP1PPP/RNBQ1RK1 w kq - 4 6"
    ctx = CheckContext.from_fens([fen])
    assert proposed_move("Спокойнее всего уйти слоном — например, сыграть Bb5 или Bc2.", ctx)[2] == "Bb5"
    assert proposed_move("Если сыграть Bb5, слон пропадает.", ctx) is None
    assert normalize_notation("а не сразу b8=Ф?") == "а не сразу b8=Q?"
