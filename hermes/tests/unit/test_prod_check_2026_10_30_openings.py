"""Prod check 29.10, theory set: opening facts said from memory where the ECO book on the server knows them —
a variation named after the wrong person (2.c3 «атака в стиле Алёхина», the Alapin), a variation claimed of a
board that has not reached it («Открытый вариант сицилианской» on 1.e4 c5), a wrong ECO code. Closed by
src/answer_check_openings.py; the book's moves and their names reach the model in the opening line of the prompt
(src/voice_engine_note._book_moves). «Обычно играют X» (can-kg-accept) is not judged: the book counts no games
(review 30.10)."""

import chess
import pytest
from fastapi.testclient import TestClient

from src.answer_check import CheckContext, _split_sentences, check_sentence


def _board(moves: str) -> chess.Board:
    board = chess.Board()
    for san in moves.split():
        board.push_san(san)
    return board


def _ctx(moves: str, question: str = "", ideas: tuple = (), game: bool = False) -> CheckContext:
    """The check context the text coach builds: the board, then the positions the student's idea leads to."""
    board = _board(moves)
    fens = [board.fen()]
    for idea in ideas:
        after = board.copy()
        after.push_san(idea)
        fens.append(after.fen())
    ctx = CheckContext.from_fens(fens, question=question)
    if game:
        ctx.game_moves = moves.split()
    return ctx


def _answer(ctx: CheckContext, text: str) -> list:
    """Every sentence of an answer checked in order, as SentenceGate does: [(sentence, issues)]."""
    sentences, rest = _split_sentences(text + " ")
    return [(s.strip(), check_sentence(s, ctx)) for s in sentences + [rest] if s.strip()]


SICILIAN = "e4 c5"
KG = "e4 e5 f4"
MORPHY = "e4 e5 Nf3 Nc6 Bb5 a6"


# ── the production answers ───────────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_move_sicilian_2_the_open_variation_and_an_alekhine_attack_are_read_back():
    ctx = _ctx(SICILIAN, "Какие ходы за белых тут считаются главными по теории?")
    out = _answer(ctx, (
        "Открытый вариант сицилианской защиты, и у белых тут три главных пути.\n\n"
        "Главный, «книжный» — **2. Кf3**: белые сразу развивают коня и готовят d2-d4, не выпуская чёрных из "
        "напряжения.\n\n"
        "Рядом стоят **2. Кc3** (спокойно, готовим тот же d4) и **2. c3** (система с последующим d4, любимая атака "
        "в стиле Алёхина).\n\n"
        "А ты сам что здесь хотел сыграть — какую идею видел за белых?"))
    flagged = {s[:20]: issues for s, issues in out if issues}
    assert set(flagged) == {"Открытый вариант сиц", "Рядом стоят **2. Кc3"}
    assert "has not reached the Sicilian Defense: Open" in flagged["Открытый вариант сиц"][0]
    assert "Sicilian Defense (B20)" in flagged["Открытый вариант сиц"][0]
    issue = flagged["Рядом стоят **2. Кc3"][0]
    assert "after 2.c3" in issue and "Alapin Variation (B22)" in issue and "Alekhine" in issue


@pytest.mark.unit
def test_can_kg_accept_usually_is_not_judged_by_the_book():
    # 3.Nc3 after 2.f4 exf4 is rare in practice, but the book cannot say so: it names lines and counts no games
    # (the Evans Gambit has 51 named sub-lines after 3...Bc5, 4.d3 five). Hermes ships no move statistics, so
    # «обычно» stays unjudged rather than cut correct teaching (review 30.10).
    ctx = _ctx(KG, "Стоит ли брать пешку f4?", ideas=("exf4",))
    assert not [i for i in check_sentence("Смотри, что дальше: белый конь обычно идёт на c3, прикрывая поле e2.", ctx)
                if "usual" in i]


@pytest.mark.unit
def test_op_ruy_and_move_ruy_main_are_right_by_the_book_and_pass():
    # The grader called C70 wrong for 3...a6 (C68 «by the Lichess table»): the book Hermes ships says C70.
    ctx = _ctx(MORPHY, "Как называется этот вариант?")
    assert check_sentence("Это испанская партия, вариант Морфи — в книге дебютов он идёт под кодом C70.", ctx) == []
    ctx = _ctx(MORPHY, "Какой здесь основной теоретический ход за белых?")
    out = _answer(ctx, (
        "Основной ход здесь — **4. Сa4** (отступление слоном, «отход Морфи»). Пешка a6 напала на слона b5, и его надо "
        "спасать: Сa4 сохраняет давление на коня c6 и уводит слона с боя.\n\n"
        "Дальше чёрные обычно играют Кf6, и после Кc3 и b5 слон уходит на b3 — испанская партия, вариант Морфи (C70)."))
    assert all(not issues for _, issues in out), out


@pytest.mark.unit
@pytest.mark.parametrize("moves, text", [
    ("d4 d5 c4 c6", "Это **славянская защита** (Slav Defense, D10)."),
    ("d4 Nf6 c4 e6 Nc3 Bb4", "Это защита Нимцовича — Ни́мцо-Индийская, ECO-код E20."),
])
def test_name_slav_and_name_nimzo_codes_are_the_books(moves, text):
    assert check_sentence(text, _ctx(moves, "Как называется эта защита?")) == []


# ── the same classes, other words ────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("moves, question, text, wrong", [
    (SICILIAN, "Как называется этот вариант?", "Это открытый вариант сицилианской защиты.", "Sicilian Defense: Open"),
    (SICILIAN, "Что это за вариант?", "Перед нами закрытый вариант сицилианской.", "Sicilian Defense: Closed"),
    (SICILIAN, "What variation is this?", "This is the Open Sicilian here.", "Sicilian Defense: Open"),
    ("e4 e6 d4 d5", "Какой это вариант?", "Это разменный вариант французской защиты.", "French Defense: Exchange"),
])
def test_a_variation_the_board_has_not_reached_is_read_back(moves, question, text, wrong):
    issues = check_sentence(text, _ctx(moves, question))
    assert any("has not reached the " + wrong in i for i in issues), issues


@pytest.mark.unit
@pytest.mark.parametrize("moves, text, real, person", [
    (SICILIAN, "2.c3 — вариант Алёхина: белые готовят d4.", "Alapin Variation", "Alekhine"),
    (SICILIAN, "А 2. c3 — это система Найдорфа.", "Alapin Variation", "Najdorf"),
    (MORPHY, "Лучше всего 4.Сa4 — вариант Свешникова.", "Morphy Defense", "Sveshnikov"),
    (SICILIAN, "Есть ещё 2.c3, the Winawer Variation.", "Alapin Variation", "Winawer"),
    # the move written right after the name, past a contrast (review 30.10)
    (SICILIAN, "Главное продолжение — 2.Кf3 d6 3.d4, а вариант Алёхина 2.c3 спокойнее.", "Alapin Variation",
     "Alekhine"),
])
def test_a_person_named_for_a_move_must_name_a_book_line_through_it(moves, text, real, person):
    issues = check_sentence(text, _ctx(moves))
    assert any(real in i and f"named after {person}" in i for i in issues), issues


@pytest.mark.unit
@pytest.mark.parametrize("moves, text, code", [
    (MORPHY, "Это испанская партия, C65.", "C65"),
    (SICILIAN, "На доске сицилианская защита (B90).", "B90"),
    ("d4 d5 c4 c6", "Это славянская защита, код D30.", "D30"),
    # a bare code answering the question for the board's code; a code tied by «это» past another clause
    (MORPHY, "Код — C68.", "C68"),
    ("d4 d5 c4 e6", "Принятый гамбит — это D20, а у нас на доске D20 тоже.", "D20"),
])
def test_a_wrong_eco_code_is_read_back(moves, text, code):
    issues = check_sentence(text, _ctx(moves, "Какой код у этого дебюта?"))
    assert any(i.startswith(f"{code} is not the ECO code") for i in issues), issues


# ── what must pass: right names, other positions, hypotheticals, plans, denials ──────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("moves, question, text", [
    # codes: a range, another opening named, a condition, the stages on the way, a line the answer writes
    (MORPHY, "", "Испанская партия занимает коды C60–C99."),
    (MORPHY, "", "В отличие от итальянской партии (C50), здесь слон давит на коня."),
    (MORPHY, "", "Если бы чёрные сыграли Кf6, это был бы C65."),
    (MORPHY, "Как называется дебют?", "Это испанская партия (C60), а после 3...a6 — вариант Морфи, C70."),
    (MORPHY, "", "После 4.Сa4 Кf6 5.O-O получается уже C78."),
    (SICILIAN, "", "Сицилианская защита — это B20, а вариант Найдорфа — B90."),
    # names: the right person, a hedge, a line of moves, a plan, a variation the board has reached
    (SICILIAN, "", "2.c3 — вариант Алапина: белые готовят d4."),
    (SICILIAN, "", "Есть ещё 2.c3, the Alapin Variation."),
    (SICILIAN, "Как называется этот вариант?", "Не путай это с вариантом Алапина."),
    (SICILIAN, "", "2. Кf3 — путь к открытому варианту."),
    (SICILIAN, "Как называется этот вариант?", "Открытый вариант сицилианской возникает после 2.Кf3 и 3.d4."),
    (SICILIAN, "Как называется этот вариант?", "Это может перейти в открытый вариант сицилианской."),
    (SICILIAN, "Как называется этот вариант?", "Это сицилианская защита; открытый вариант будет, если белые сыграют d4."),
    ("e4 c5 Nf3 Nc6 d4 cxd4 Nxd4", "Как называется этот вариант?", "Это открытый вариант сицилианской защиты."),
    # the Open Sicilian with 2...d6: the book names it otherwise, which is no proof the words are wrong
    ("e4 c5 Nf3 d6 d4 cxd4 Nxd4", "Как называется этот вариант?", "Это открытый вариант сицилианской защиты."),
    (MORPHY, "Как называется этот вариант?", "Это вариант Морфи испанской партии."),
    (MORPHY, "", "Лучше всего 4.Сa4 — дальше бывает и вариант Тарраша."),  # 4...Nf6 5.Nc3: a line through 4.Ba4
    ("e4 Nf6 e5", "", "Если играешь защиту Алехина, конь на f6 уходит на d5."),
    ("e4 c6", "", "Спокойнее и надёжнее — 2.d3, вариант Брейера."),
    ("", "Покажи на доске защиту Каро-Канн", "Спокойнее и надёжнее — 2.d3, вариант Брейера."),
    # review 30.10 — «usually» / «the main move» is not judged by line counts: the Giuoco Pianissimo, the English
    # 2.Nc3, the London's 2.Bf4, the student's own habit, a player, beginners, a time control, a piece word
    ("e4 e5 Nf3 Nc6 Bc4 Bc5", "Какой план у белых?", "Здесь белые обычно играют 4.d3: спокойно укрепляют центр."),
    ("c4 Nf6", "Какой ход здесь главный?", "Главный ход здесь — 2.Кc3: белые остаются в английском начале."),
    ("d4 Nf6", "Я играю лондонскую систему, что дальше?", "В лондонской системе здесь обычно играют 2.Сf4."),
    ("e4", "Что я обычно отвечаю на e4?", "Против 1.e4 ты чаще всего играешь 1...d5 — в 40 партиях из последних."),
    ("e4 e5", "", "Здесь новички обычно играют Фh5, но это слабо."),
    ("e4 e5", "", "Здесь Карлсен обычно играет Кc3."),
    ("e4 e5", "", "В блице здесь обычно играют Сc4."),
    ("e4 e5", "", "Дальше белые обычно играют конём f3."),
    ("e4 e5 Nf3 Nc6 Bc4", "", "Дальше чёрные обычно отвечают 3...Сe7 — венгерская защита."),
    # review 30.10 — a variation ahead, possible, a choice, the popular one, advice, a relative
    (SICILIAN, "Как называется этот дебют?", "Это сицилианская защита, и вариант Найдорфа здесь ещё впереди."),
    (SICILIAN, "Как называется этот дебют?",
     "Это сицилианская защита, а самый популярный её вариант здесь — вариант Найдорфа."),
    (SICILIAN, "What variation is this?",
     "It's the Sicilian Defense, and the Open Sicilian is White's most popular choice here."),
    (SICILIAN, "Как называется этот дебют?", "Это сицилианская защита — здесь возможен и вариант Алапина, и открытый вариант."),
    ("e4 e6 d4 d5 Nc3", "Как называется?",
     "Это французская защита: здесь начинается выбор между вариантом Винавера и классической системой."),
    ("e4 c5 Nf3 d6 Bb5+", "Как называется вариант?", "Это московский вариант, родственник варианта Россолимо."),
    # review 30.10 — the name goes with the move written right after it, not with the last move of another clause
    (SICILIAN, "Какие главные ходы?", "Главное продолжение — 2.Кf3 d6 3.d4, а вариант Алапина 2.c3 считается более спокойным."),
    # review 30.10 — names the book gives narrower than players do: a sub-line of the variation the board is in, a
    # surname the book spreads over many openings
    ("e4 c5 Nf3 Nc6 d4 cxd4 Nxd4 Nf6 Nc3 e5", "Как называется этот вариант?", "Это вариант Свешникова."),
    ("d4 Nf6 c4 e6 Nc3 Bb4 Qc2", "Как называется этот вариант?", "Это вариант Капабланки."),
    ("d4 Nf6 c4 e6 Nc3 Bb4", "", "Самое популярное здесь — 4.Фc2, вариант Капабланки."),
    ("e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O h3 Bb7", "Как называется этот вариант?",
     "Это вариант Зайцева."),
    # review 30.10 — a code in a clause about another opening, the student's options, a player, a bare surname
    ("d4 d5 c4 e6", "Код?", "Это отказанный ферзевый гамбит — D30, а принятый гамбит идёт под D20."),
    ("e4 e5 Nf3 Nc6 Bb5 Nf6", "Код?", "Это берлинка, C65; берлинский эндшпиль — C67."),
    ("d4 d5 c4", "", "Принять гамбит — D20, отказаться — D30."),
    ("d4 d5 c4", "", "Взяв на c4, чёрные получат D20."),
    (MORPHY, "", "Карлсен часто играет C67."),
    (SICILIAN, "", "Свешников (B33) — острый вариант."),
    (SICILIAN, "", "Схевенинген — B80, Найдорф — B90."),
    (SICILIAN, "", "Например, дракон — это B70."),
])
def test_right_or_other_position_opening_facts_pass(moves, question, text):
    ctx = (CheckContext.from_fens([moves], question=question) if "/" in moves
           else _ctx(moves, question))
    issues = [i for i in check_sentence(text, ctx)
              if "ECO" in i or "usual move" in i or "named after" in i or "has not reached" in i]
    assert issues == [], issues


@pytest.mark.unit
def test_a_variation_ahead_that_the_turn_shows_is_not_condemned():
    # The student steps through the Open Sicilian loaded on the board: the board is on the way to the line.
    ctx = CheckContext.from_fens([_board(SICILIAN).fen()], ["1. e4 c5 2. Nf3 Nc6 3. d4 cxd4 4. Nxd4"],
                                 question="Как называется этот вариант?")
    assert not [i for i in check_sentence("Это открытый вариант сицилианской защиты.", ctx) if "has not reached" in i]


@pytest.mark.unit
def test_a_code_a_tool_gave_is_the_coachs_to_repeat():
    ctx = _ctx(MORPHY)
    assert check_sentence("Это C65.", ctx)  # nothing on the board or in the turn has C65
    ctx.add_text('{"eco": "C65", "name": "Ruy Lopez: Berlin Defense", "pgn": "1. e4 e5 2. Nf3 Nc6 3. Bb5 Nf6"}')
    assert not [i for i in check_sentence("Это C65.", ctx) if "ECO" in i]


@pytest.mark.unit
def test_the_game_on_the_board_gives_its_stages():
    ctx = _ctx("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6 Be2 e5 Nb3 Be7 O-O O-O", game=True)
    assert not [i for i in check_sentence("Мы разыграли сицилианскую, вариант Найдорфа — B92.", ctx) if "ECO" in i]
    assert [i for i in check_sentence("Мы разыграли сицилианскую защиту, код B33.", ctx) if "ECO" in i]


# ── the book's moves in the prompt, and the voice coach's check ──────────────────────────────────────────────

@pytest.mark.unit
def test_the_prompt_gives_the_books_moves_with_their_names_and_no_ranking():
    from src.voice_engine_note import _book_moves

    line = _book_moves(_board(SICILIAN).fen())
    assert "2.c3 — Sicilian Defense: Alapin Variation (B22)" in line and "2.Nf3" in line
    kg = _book_moves(_board("e4 e5 f4 exf4").fen())
    assert "3.Nf3 — King's Gambit Accepted: King's Knight's Gambit (C34)" in kg
    # review 30.10: line counts are no popularity — the Evans is not offered as «the main / usual move»
    italian = _book_moves(_board("e4 e5 Nf3 Nc6 Bc4 Bc5").fen())
    assert "book lines" not in italian and "call only the first" not in italian
    assert "says nothing of which move is main or usual" in italian
    assert _book_moves("8/8/8/4k3/8/8/4K3/8 w - - 0 1") is None


@pytest.mark.unit
def test_the_voice_check_reads_the_same_opening_facts():
    from src.server import app

    client = TestClient(app)
    resp = client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-openings"}, json={
        "text": "Дальше белые обычно играют конь эф три.", "fen": _board("e4 e5").fen(),
    })
    assert not [i for i in resp.json()["issues"] if "usual" in i]  # review 30.10
    resp = client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-openings"}, json={
        "text": "Это сицилианская защита, а вариант Найдорфа здесь ещё впереди.", "fen": _board(SICILIAN).fen(),
        "question": "Как называется этот дебют?",
    })
    assert not [i for i in resp.json()["issues"] if "has not reached" in i]
    resp = client.post("/api/coach/voice/check", headers={"X-User-Id": "voice-openings"}, json={
        "text": "Рядом стоит 2. c3 — любимая атака в стиле Алёхина.", "fen": _board(SICILIAN).fen(),
    })
    assert any("named after Alekhine" in i for i in resp.json()["issues"])


def test_the_position_index_is_never_built_on_the_event_loop(monkeypatch):
    # Review 30.10: the first sentence with an ECO code after a restart built the book's position index (0.9 s) in
    # the text gate, on the event loop. There it is built in the background; the sentence waits for nothing.
    import asyncio
    import threading

    import src.openings_book as ob

    book = ob.get_book()
    built = threading.Event()
    monkeypatch.setattr(book, "_by_position", None)
    monkeypatch.setattr(ob, "warm_position_index", lambda: built.set())
    ctx = _ctx("e4 c5")

    async def turn():
        return check_sentence("Это сицилианская защита, ECO C60.", ctx)

    assert not [i for i in asyncio.run(turn()) if "ECO code" in i]  # not built yet: not judged
    assert built.wait(5)  # built in the background meanwhile


def test_off_the_event_loop_the_index_is_built_and_used(monkeypatch):
    import src.openings_book as ob

    monkeypatch.setattr(ob.get_book(), "_by_position", None)
    issues = check_sentence("Это сицилианская защита, ECO C60.", _ctx("e4 c5"))
    assert any(i.startswith("C60 is not the ECO code") for i in issues), issues
