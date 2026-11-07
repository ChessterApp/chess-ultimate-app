"""Whose side the student plays, decided once by the server (src/student_side.py, 06.11).

The old bug (measured on shipped1104/fp, cases t25, t46): a question that tells the opponent's last move — «Они
сыграли f5. Брать?», «Белые поставили коня на d5. Брать?» — made the student the side that had just moved (the
«already played» reading of src/server meant «I played it»), and the answer check then cut «Твой конь b5 нападает на
пешку c7» and «Белый конь d5 под боем твоей пешки e6» as the other side's pieces. The side is now decided in one place
from the game, the student's own words («я играю чёрными», "I'm Black", «мен ақпен ойнаймын») and who the question
says made a move («они/соперник/they/олар» vs «я/I/мен»), with the mover's colour read off the board and its record —
and the same decision goes to the model (a turn-context block, the rewrite's side note) and to every check."""

import json

import chess
import pytest
from fastapi.testclient import TestClient

# shipped1104/fp p25 (English, 17.h4 … 16...f5; White to move) and p46 (Sicilian puzzle, Black to move).
P25_MOVES = ("c4 e5 Nc3 Nf6 Nf3 Nc6 g3 d5 cxd5 Nxd5 Bg2 Nb6 a4 a5 O-O Bb4 Qc2 h6 Rd1 Qe7 d3 Bg4 Nb5 O-O h3 Be6 e4 "
             "Rad8 Be3 g5 h4 f5").split()
P46 = "3qk2r/3b1pbp/B2ppp2/P2N4/1Q2PP2/8/1Pr3PP/R3K2R b KQk - 0 16"
P28 = "3r1rk1/pp3ppp/1q2p3/bB1b4/Pn1P4/1P2QN2/3B1PPP/2R2RK1 b - - 0 17"
P30 = "3r4/8/4k1p1/1pb2p2/1P3P2/2R3P1/8/5K2 w - - 0 52"
QB6 = "k7/8/1Q6/8/8/8/8/2K5 b - - 0 1"


def _board(moves):
    b = chess.Board()
    for s in moves:
        b.push_san(s)
    return b


def _moves(moves):
    b = chess.Board()
    out = []
    for s in moves:
        mv = b.parse_san(s)
        out.append(mv)
        b.push(mv)
    return out


P25 = _board(P25_MOVES).fen()
P25_PGN = chess.Board().variation_san(_moves(P25_MOVES))


def app_():
    from src.server import app

    return app


def _turn(monkeypatch, user, question, fen, answer, pgn=None):
    """One text turn through /api/coach/chat with a scripted answer; returns what the student was shown."""
    from unittest.mock import MagicMock, patch

    from src import config
    from src.sessions import session_store
    from src.user_profile import UserProfile

    for name, value in {"COACH_TWO_STAGE": False, "COACH_ENGINE_NOTE": False, "COACH_OPENING_PRESTEP": False,
                        "COACH_HYPOTHETICAL_NOTE": False, "COACH_ANSWER_FIX": False, "COACH_ANSWER_CHECK": True,
                        "COACH_PUZZLE_PRESTEP": False}.items():
        if hasattr(config, name):
            monkeypatch.setattr(config, name, value)
    session = session_store.create(user_id=user)
    if pgn:
        board = session.add_board(kind="study", pgn=pgn, fen=fen)
        session.set_active_board(board.id) if hasattr(session, "set_active_board") else None
    session.board_state = fen
    seen = {}
    agent = MagicMock()
    agent.tools, agent._api_call_count, agent.max_iterations = [], 1, 5
    agent.session_prompt_tokens = agent.session_completion_tokens = 0

    def chat(message, stream_callback=None):
        seen["message"] = message
        stream_callback(answer)
        return answer

    agent.chat.side_effect = chat
    with patch("src.server._create_agent", return_value=agent), \
            patch("src.server.load_user_profile", return_value=UserProfile(user_id=user)), \
            patch("src.server.log_event"):
        resp = TestClient(app_()).post("/api/coach/chat", headers={"X-User-Id": user},
                                       json={"message": question, "session_id": session.id, "fen": fen,
                                             "locale": "ru"})
    shown = "".join(json.loads(ln[6:]).get("delta", "") for ln in resp.text.splitlines() if ln.startswith("data: "))
    return shown, seen.get("message", "")


# ── the recorded cases, through the server ─────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_t25_they_played_f5_keeps_the_student_white(monkeypatch):
    from src import config

    monkeypatch.setattr(config, "COACH_STUDENT_SIDE", "on", raising=False)
    true = "Твой конь b5 нападает на пешку c7, но её защищает ферзь e7."
    shown, model_saw = _turn(monkeypatch, "side-t25", "Они сыграли f5. Брать?", P25,
                             "Чёрные сыграли f5 и нападают на пешку e4. " + true, pgn=P25_PGN)
    assert true in shown, shown
    assert "The student plays White" in model_saw


@pytest.mark.unit
def test_t46_white_put_the_knight_on_d5_keeps_the_student_black(monkeypatch):
    from src import config

    monkeypatch.setattr(config, "COACH_STUDENT_SIDE", "on", raising=False)
    true = "Белый конь d5 под боем твоей пешки e6."
    shown, _ = _turn(monkeypatch, "side-t46", "Белые поставили коня на d5. Брать?", P46, true + " Это важно.")
    assert true in shown, shown


@pytest.mark.unit
def test_i_played_qb6_still_makes_the_student_white(monkeypatch):
    from src import config

    monkeypatch.setattr(config, "COACH_STUDENT_SIDE", "on", raising=False)
    # The case the old «already played» rule was written for (2026-10-08) keeps working: «твой ферзь на b6».
    _shown, model_saw = _turn(monkeypatch, "side-qb6", "Я сыграл Qb6. Это мат?", QB6, "Твой ферзь на b6 стоит рядом с королём.")
    assert "The student plays White" in model_saw and "Black's (the opponent's) move now" in model_saw


@pytest.mark.unit
def test_a_guessed_side_is_not_told_to_the_model(monkeypatch):
    _shown, model_saw = _turn(monkeypatch, "side-guess", "Что здесь играть?", P46, "Подумай о размене.")
    assert "## The student's side" not in model_saw


# ── the decision ───────────────────────────────────────────────────────────────────────────────────────────────

from src.student_side import StudentSide, check_color, decide  # noqa: E402

W, B = chess.WHITE, chess.BLACK


@pytest.mark.unit
@pytest.mark.parametrize("question,fen,pgn,color,source", [
    # the opponent's move told — RU / EN / KK; the move's colour from the record, from the piece standing there
    ("Они сыграли f5. Брать?", P25, None, W, "their_move"),
    ("Они сыграли f5. Брать?", P25, P25_PGN, W, "their_move"),
    ("Соперник сыграл f5, что делать?", P25, None, W, "their_move"),
    ("Противник пошёл f5 — брать?", P25, P25_PGN, W, "their_move"),
    ("Мой соперник только что сыграл f5", P25, None, W, "their_move"),
    ("They played f5. Should I take?", P25, None, W, "their_move"),
    ("My opponent played f5, what now?", P25, None, W, "their_move"),
    ("Олар f5 жүрді. Алайын ба?", P25, None, W, "their_move"),
    ("Қарсылас f5 жүрді, не істеймін?", P25, None, W, "their_move"),
    ("Они сыграли b3. Что теперь?", P28, None, B, "their_move"),
    ("Они взяли моего слона на c5!", P30, None, W, "their_move"),
    # the student's own move told
    ("Я сыграл Qb6. Это мат?", QB6, None, W, "own_move"),
    ("I played Qb6 — is it mate?", QB6, None, W, "own_move"),
    ("Мен Qb6 жүрдім. Бұл мат па?", QB6, None, W, "own_move"),
    ("Qb6 жүрдім, мат па?", QB6, None, W, "own_move"),
    ("I played Nb5 and they replied f5. Now what?", P25, P25_PGN, W, "own_move"),
])
def test_who_made_the_move_decides(question, fen, pgn, color, source):
    side = decide(question, fen, pgn=pgn)
    assert (side.color, side.source) == (color, source), side
    assert side.exact


@pytest.mark.unit
@pytest.mark.parametrize("question,color", [
    ("Я играю чёрными, что здесь делать?", B),
    ("я за белых", W),
    ("У меня белые, как продолжать?", W),
    ("Что делать чёрными?", B),
    ("Как играть за белых в этой позиции?", W),
    ("I'm playing Black here, what now?", B),
    ("I play white. Plan?", W),
    ("What should I play as Black?", B),
    ("My pieces are black.", B),
    ("Мен ақпен ойнаймын, не істеймін?", W),
    ("Мен қаралармен ойнаймын", B),
    ("Менде қаралар, жоспар қандай?", B),
    ("Ақтар үшін не істеу керек?", W),
])
def test_the_side_the_student_says(question, color):
    for fen in (P25, P46):  # whoever is to move
        side = decide(question, fen)
        assert (side.color, side.source) == (color, "said"), (question, fen, side)


@pytest.mark.unit
@pytest.mark.parametrize("question,fen", [
    # a colour as the subject is a story about the game, not the student's opponent («почему белые сыграли Bxf7?»)
    ("Белые поставили коня на d5. Брать?", P46),
    ("Почему белые сыграли Nd5?", P46),
    ("Why did White play Nd5?", P46),
    ("Ақтар Nd5 жүрді", P46),
    # «он/она», "he": a piece as often as the opponent
    ("Он пошёл на d5, брать?", P46),
    # nothing told, nothing said
    ("Что здесь играть?", P46),
    ("Что если я возьму на c5?", P30),
    # a denial is not a move told
    ("Я не играл f5, это они.", P25),
])
def test_no_exact_side_falls_back_to_the_side_to_move(question, fen):
    side = decide(question, fen)
    assert not side.exact and check_color(side) is None
    if side.source == "side_to_move":
        assert side.color == chess.Board(fen).turn


@pytest.mark.unit
def test_two_told_moves_that_disagree_leave_it_unknown():
    # Nb5 and h3 were both White's in the record: «I» for one and «they» for the other cannot both be true.
    side = decide("Я сыграл Nb5, а они ответили h3", P25, pgn=P25_PGN)
    assert side.color is None and side.source == "conflict"


@pytest.mark.unit
def test_said_and_told_that_disagree_leave_it_unknown():
    side = decide("Я играю чёрными. Они сыграли f5.", P25)  # f5 was Black's: «they» are Black — not the student
    assert side.color is None and side.source == "conflict" and check_color(side) is None


@pytest.mark.unit
def test_a_move_to_come_is_the_side_that_can_play_it():
    # Black to move: «если они сыграют Rxb2» — only Black can → the student is White; «если я сыграю Rxb2» — Black.
    assert decide("Что если они сыграют Rxb2?", P46).color == W
    assert decide("Что если я сыграю Rxb2?", P46).color == B
    assert decide("What if they play Rxb2?", P46).color == W


@pytest.mark.unit
def test_the_game_decides_over_words():
    side = decide("Я играю чёрными", P25, game_state={"student_color": "white", "moves": []})
    assert (side.color, side.source) == (W, "game")
    assert side.note(chess.Board(P25)) == ""  # the game block tells it already


@pytest.mark.unit
def test_the_note_names_the_side_and_whose_move_it_is():
    note = decide("Они сыграли f5. Брать?", P25).note(chess.Board(P25))
    assert "The student plays White" in note and "Они сыграли f5" in note and "Black is the opponent" in note
    assert "move now" not in note  # White is to move: the student's own move
    assert decide("Что здесь играть?", P25).note(chess.Board(P25)) == ""
    assert StudentSide(None, "none").note() == ""


# ── the checks get the same decision ──────────────────────────────────────────────────────────────────────────

from src.answer_check import CheckContext, check_sentence  # noqa: E402


def _ctx(question, fen, pgn=None):
    side = decide(question, fen, pgn=pgn)
    ctx = CheckContext.from_fens([fen], [pgn] if pgn else [], question=question, student_color=check_color(side))
    ctx.student_side_why = side.why()
    return ctx


@pytest.mark.unit
@pytest.mark.parametrize("question", ["Они сыграли f5. Брать?", "They played f5. Should I take?", "Олар f5 жүрді. Алайын ба?"])
def test_the_students_piece_after_the_opponents_move_is_not_cut(question):
    ctx = _ctx(question, P25, P25_PGN)
    assert ctx.student_color == W
    assert check_sentence("Твой конь b5 нападает на пешку c7.", ctx) == []
    assert check_sentence("Your knight on b5 attacks the c7 pawn.", ctx) == []


@pytest.mark.unit
def test_the_opponents_piece_called_yours_is_still_caught():
    ctx = _ctx("Они сыграли f5. Брать?", P25, P25_PGN)
    issues = check_sentence("Твоя пешка f5 нападает на e4.", ctx)
    assert any("f5" in i and "Black" in i for i in issues), issues


@pytest.mark.unit
def test_a_said_side_against_the_side_to_move_is_used_by_the_checks():
    # Black says so on a board where White is to move (they set it up for the opponent's move)
    ctx = _ctx("Я играю чёрными. Что сделают белые?", P25)
    assert ctx.student_color == B
    assert check_sentence("Твой ферзь e7 защищает пешку c7.", ctx) == []
    assert check_sentence("Твой конь b5 нападает на пешку c7.", ctx)


@pytest.mark.unit
def test_the_rewrite_note_says_why():
    from src.server import _student_side_note

    ctx = _ctx("Они сыграли f5. Брать?", P25, P25_PGN)
    note = _student_side_note(ctx)
    assert "The student plays White" in note and "opponent's move" in note
    guessed = _ctx("Что здесь играть?", P46)
    assert "Black (the side to move on the board)" in _student_side_note(guessed)


# ── the voice check reads the spoken question the same way ────────────────────────────────────────────────────

@pytest.mark.unit
def test_the_voice_check_keeps_the_students_piece_after_the_opponents_move():
    from unittest.mock import patch

    async def _no_limit(*a, **k):
        return None

    client = TestClient(app_())
    with patch("src.server.enforce_rate_limit", side_effect=_no_limit), patch("src.server.log_event"):
        r = client.post("/api/coach/voice/check", headers={"X-User-Id": "side-voice"},
                        json={"text": "Твой конь b5 нападает на пешку c7.", "fen": P25, "pgn": P25_PGN,
                              "question": "Они сыграли f5. Брать?", "engine": False})
        bad = client.post("/api/coach/voice/check", headers={"X-User-Id": "side-voice"},
                          json={"text": "Твоя пешка f5 нападает на e4.", "fen": P25, "pgn": P25_PGN,
                                "question": "Они сыграли f5. Брать?", "engine": False})
    assert r.status_code == 200 and r.json()["issues"] == [], r.json()
    assert bad.json()["issues"], bad.json()


# shipped1104/fp t09: the Vienna after 3.f4 d5 4.d3 exf4 — «они взяли на f4» is 4...exf4 (Black's), not the pawn move
# 3.f4 the record also has; the first cut of this decision read «f4» as 3.f4 and made the student Black.
VIENNA = "rnbqkb1r/ppp2ppp/5n2/3p4/4Pp2/2NP4/PPP3PP/R1BQKBNR w KQkq - 0 5"
VIENNA_PGN = "1. e4 e5 2. Nc3 Nf6 3. f4 d5 4. d3 exf4"


@pytest.mark.unit
@pytest.mark.parametrize("question", [
    "Венский гамбит, они взяли на f4. Бить слоном?",
    "Соперник взял на f4, бить слоном?",
    "They took on f4. Should my bishop take?",
    "Олар f4-ке алды. Пілмен алайын ба?",
])
@pytest.mark.parametrize("pgn", [VIENNA_PGN, None])
def test_a_square_taken_on_is_the_capture_not_the_pawn_move(question, pgn):
    side = decide(question, VIENNA, pgn=pgn)
    assert (side.color, side.source) == (W, "their_move"), side
    ctx = _ctx(question, VIENNA, pgn)
    assert check_sentence("Пешка f4 не защищена, её атакует твой слон c1.", ctx) == []


# ── review 06.11: subjects that play no move, colours that are objects, the dropped «я», the shadow switch ─────────

E4E5 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
ITALIAN = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"
RUY = "r1bqkbnr/1ppp1ppp/p1n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4"
RUY_BA4 = "r1bqkbnr/1ppp1ppp/p1n5/4p3/B3P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 1 4"  # after 4.Ba4: the bishop stands there


@pytest.mark.unit
@pytest.mark.parametrize("question,fen", [
    # the engine recommends, it is not the opponent; an object is not a subject; an unplayed move told as done
    ("Движок советует Nf3. Почему?", E4E5),
    ("The engine suggests Nf3 here, why?", E4E5),
    ("Что угрожает сопернику после Nf3?", E4E5),
    ("Почему здесь они сыграли Nf3?", E4E5),
    # a side named, not the student's: the opponent's reply, an object, a possessive, a square colour
    ("What's the best move for Black here?", E4E5),
    ("I have black's knight pinned", E4E5),
    ("Как атаковать чёрных?", E4E5),
    ("Как лучше атаковать чёрных на ферзевом фланге?", E4E5),
    ("У меня белые поля слабые", E4E5),
    ("I have the white-squared bishop", E4E5),
    # «я» with no move verb: stopping the opponent's threat
    ("Я боюсь Ng5, как защититься?", ITALIAN),
    ("Как я могу помешать Ng5?", ITALIAN),
    ("How can I stop Ng5?", ITALIAN),
    ("I am worried about Ng5. What now?", ITALIAN),
    # a colour subject nearer the move than «я»; Russian instrumentals are no Kazakh verb
    ("Я думаю, белые сыграли Ba4 зря", RUY_BA4),
    ("Я разбираю партию Карлсена: почему белые сыграли Ba4?", RUY_BA4),
    ("Почему белые сыграли Ba4 четвёртым ходом?", RUY_BA4),
    ("Почему белые сыграли Bb5 простым развитием?", RUY),
    ("Можно сыграть Nc3 простым ходом?", E4E5),
])
def test_review_1106_no_exact_side(question, fen):
    side = decide(question, fen)
    assert not side.exact and check_color(side) is None, (question, side)


@pytest.mark.unit
@pytest.mark.parametrize("question,fen,color,source", [
    # the dropped «я» (2026-10-08 covered it through «already played»)
    ("Сыграл Qb6. Это мат?", QB6, W, "own_move"),
    ("Пошёл ферзём на b6, мат?", QB6, W, "own_move"),
    ("А потом сыграл Qb6, мат?", QB6, W, "own_move"),
    ("Мой последний ход Qb6, мат?", QB6, W, "own_move"),
    # the student playing, with a play verb
    ("Если я сыграю Nf3, что будет?", E4E5, W, "own_move"),
    ("I want to play Nf3", E4E5, W, "own_move"),
    ("Что если соперник сыграет Ng5?", ITALIAN, B, "their_move"),
    # the side said, the phrase ending at the colour or in the instrumental / «за»
    ("У меня белые фигуры, что делать?", E4E5, W, "said"),
    ("Что делать за белых?", E4E5, W, "said"),
    ("How do I defend as Black?", E4E5, B, "said"),
    ("I have the white pieces", E4E5, W, "said"),
])
def test_review_1106_still_decided(question, fen, color, source):
    side = decide(question, fen)
    assert (side.color, side.source) == (color, source), (question, side)


@pytest.mark.unit
@pytest.mark.parametrize("question", ["Он сыграл Qb6, это мат?", "Сыграл бы Qb6?", "Карлсен сыграл Qb6"])
def test_the_dropped_i_needs_a_clause_of_its_own(question):
    assert not decide(question, QB6).exact


@pytest.mark.unit
def test_they_about_the_database_game_is_no_opponent():
    assert decide("Почему они сыграли Qb6?", QB6).source == "their_move"
    assert not decide("Почему они сыграли Qb6?", QB6, master_game=True).exact


@pytest.mark.unit
@pytest.mark.parametrize("question,fen,sentence", [
    ("Движок советует Nf3. Почему?", E4E5, "После Nf3 твой конь нападает на пешку e5."),
    ("Что угрожает сопернику после Nf3?", E4E5, "После Nf3 твой конь нападает на пешку e5."),
    ("Как я могу помешать Ng5?", ITALIAN, "Твой конь c6 защищает пешку e5."),
    ("How can I stop Ng5?", ITALIAN, "Твой конь c6 защищает пешку e5."),
    ("Как атаковать чёрных?", E4E5, "Твой конь g1 может пойти на f3."),
    ("Я думаю, белые сыграли Ba4 зря", RUY_BA4, "Твоя пешка b7 может пойти на b5."),
    ("Почему белые сыграли Ba4 четвёртым ходом?", RUY_BA4, "Твой конь c6 защищает пешку e5."),
])
def test_review_1106_true_sentences_kept_with_the_switch_on(monkeypatch, question, fen, sentence):
    from src import config

    monkeypatch.setattr(config, "COACH_STUDENT_SIDE", "on", raising=False)
    assert check_sentence(sentence, _ctx(question, fen)) == [], question


@pytest.mark.unit
@pytest.mark.parametrize("question,fen,answer", [
    ("Движок советует Nf3. Почему?", E4E5, "После Nf3 твой конь нападает на пешку e5."),
    ("The engine suggests Nf3 here, why?", E4E5, "После Nf3 твой конь нападает на пешку e5."),
    ("Что угрожает сопернику после Nf3?", E4E5, "После Nf3 твой конь нападает на пешку e5."),
    ("Сыграл Qb6. Это мат?", QB6, "Твой ферзь на b6 стоит рядом с королём."),
    ("Пошёл ферзём на b6, мат?", QB6, "Твой ферзь на b6 стоит рядом с королём."),
])
@pytest.mark.parametrize("how", ["shadow", "on"])
def test_review_1106_through_the_server(monkeypatch, question, fen, answer, how):
    from src import config

    monkeypatch.setattr(config, "COACH_STUDENT_SIDE", how, raising=False)
    shown, model_saw = _turn(monkeypatch, f"side-r-{how}", question, fen, answer)
    assert answer in shown, (question, how, shown)
    if fen == E4E5:
        assert "## The student's side" not in model_saw


@pytest.mark.unit
def test_shadow_applies_only_where_the_server_pinned_before():
    from src.student_side import applied, legacy_color

    said = decide("Я играю чёрными. Что сделают белые?", P25)
    assert said.exact
    assert check_color(applied(said, None, "shadow")) is None  # 04.11 pinned nothing here: logged only
    assert check_color(applied(said, None, "on")) == B
    told = decide("Они сыграли f5. Брать?", P25, pgn=P25_PGN)
    legacy = legacy_color([{"verdict": "already played (16...f5)"}], P25)
    assert legacy == B  # the 04.11 pin: the side that just moved
    assert check_color(applied(told, legacy, "on")) == W  # corrected under on
    assert check_color(applied(told, legacy, "shadow")) == B  # shadow: 04.11 as it was (merge review 06.11)
    assert check_color(applied(told, legacy, "off")) == B  # 04.11 as it was
    assert applied(told, legacy, "shadow").note(chess.Board(P25)) == ""
    guess = decide("Белые поставили коня на d5. Брать?", P46)
    assert check_color(applied(guess, True, "on")) is None  # the wrong pin dropped under on
    assert check_color(applied(guess, True, "shadow")) is True
    game = decide("x", P25, game_state={"student_color": "black"})
    assert check_color(applied(game, None, "shadow")) == B


@pytest.mark.unit
def test_shadow_tells_the_model_no_side_the_old_server_did_not_pin(monkeypatch):
    from src import config

    monkeypatch.setattr(config, "COACH_STUDENT_SIDE", "shadow", raising=False)
    _shown, model_saw = _turn(monkeypatch, "side-sh", "Я играю чёрными. Что сделают белые?", P25, "Подумай.")
    assert "## The student's side" not in model_saw
    monkeypatch.setattr(config, "COACH_STUDENT_SIDE", "on", raising=False)
    _shown, model_saw = _turn(monkeypatch, "side-on", "Я играю чёрными. Что сделают белые?", P25, "Подумай.")
    assert "The student plays Black" in model_saw
