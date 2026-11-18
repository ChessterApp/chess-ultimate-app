"""After a resignation the coach says what happened, never what its notes do or do not list (tester's report 18.11).

The tester played 1.e4 c5 2.Nf3 d6 against the coach and resigned. The comment: «Решающий момент — твоя сдача:
ошибок в приведённых ходах не указано» — the model wording the facts it was given (the rule said «name the moment that
decided it (from the mistakes listed, if any)», and none were listed). The review after «Разобрать» opened with «В
предыдущем ответе были приведены ходы, которых в нашей партии не было»; on production the same day «Я ошибся в прошлом
ответе, назвав Кf3 третьим ходом» — and the server itself wrote a mistake as «3. Nf3» (its ply, read as move 3).

Now the server states the decisive moment itself (src/game_mode.decisive_moment): a resignation with no mistake is «no
decisive mistake, resigning was early»; a finished game's comment gets the whole record with its numbers and a mistake
is written «2.Nf3»; the coach is told never to talk about its notes or its earlier messages (the comment's system text,
the chat's speech layer); and a sentence that still does is left out by the answer check (src/answer_check
.is_self_reference) — the comment then falls back to the plain facts, which say the same.
"""

import json
from unittest.mock import patch

import chess
import pytest
from fastapi.testclient import TestClient

from src import config, game_mode
from src.answer_check import SELF_REF_ISSUE, CheckContext, SentenceGate, is_self_reference
from src.game_mode import comment_prompt, decisive_moment, fallback_comment, game_context, play_move, resign, start_game
from src.prompt_builder import COACH_SPEECH_LAYER, PROMPT_TEMPLATE_VERSION
from src.quick_reply import QuickReply
from src.server import app
from src.sessions import session_store

USER = {"X-User-Id": "resign-user"}
TESTER = "Решающий момент — твоя сдача: ошибок в приведённых ходах не указано."


@pytest.fixture(autouse=True)
def _engine(monkeypatch):
    # The engine answers 1.e4 with c5 and 2.Nf3 with d6, and rates every position equal.
    def _move(fen, elo):
        board = chess.Board(fen)
        return board.parse_san("c5" if board.piece_at(chess.C7) else "d6").uci()

    monkeypatch.setattr(game_mode, "_engine_move", _move)
    monkeypatch.setattr(game_mode, "_evaluate", lambda fen, pov: (20, None))
    monkeypatch.setattr(config, "COACH_ANSWER_CHECK", True)


def _testers_game():
    session = session_store.create(user_id=USER["X-User-Id"])
    board, _ = start_game(session, "white", 1500)
    play_move(session, board, "e4")
    play_move(session, board, "Nf3")
    assert board.game_state["moves"] == ["e4", "c5", "Nf3", "d6"]
    resign(session, board)
    return session, board


def _completion(text):
    def fake(*, model, api_key, messages, on_delta=None, **kw):
        for i in range(0, len(text), 9):
            on_delta(text[i:i + 9])
        return QuickReply(text=text, model=model, prompt_tokens=30, completion_tokens=20)
    return fake


def _comment(session, board, text):
    with patch("src.quick_reply.stream_completion", _completion(text)), patch("src.server.log_event"):
        resp = TestClient(app).post(f"/api/coach/sessions/{session.id}/game/{board.id}/comment", headers=USER,
                                    json={"locale": "ru", "event": "end"})
    frames = [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: ")]
    return "".join(f.get("delta", "") for f in frames).strip()


@pytest.mark.unit
class TestTheFacts:
    def test_a_resignation_with_no_mistake_is_told_as_one(self):
        """The server says what decided the game: nothing on the board — resigning was early."""
        _, board = _testers_game()
        moment = decisive_moment(board.game_state)
        assert "NO decisive mistake" in moment and "resigning was early" in moment and "after 2 moves" in moment

    def test_the_end_comment_gets_the_whole_record_and_the_decisive_line(self):
        """The model words a fact it is given, instead of reasoning about a list that is empty."""
        _, board = _testers_game()
        system, facts = (m["content"] for m in comment_prompt(board, "ru", event="end"))
        assert "The game's moves (the whole record): 1.e4 c5 2.Nf3 d6" in facts
        assert "NO decisive mistake" in facts and "Student's mistakes" not in facts
        assert "from the mistakes listed" not in system and "«Decisive moment» line" in system

    def test_the_comment_is_told_never_to_talk_about_its_notes(self):
        _, board = _testers_game()
        system = comment_prompt(board, "ru", event="end")[0]["content"]
        assert "never mention them or what they list or do not list" in system
        assert "never refer to your own earlier messages" in system

    def test_a_mistake_is_written_with_its_move_number_not_its_ply(self):
        """«3. Nf3» was the ply: the model read it as the third move. It is 2.Nf3 — and 2...d6 for Black's."""
        state = {"annotations": [{"ply": 3, "san": "Nf3", "verdict": "mistake", "cp_loss": 120, "best": "d4"},
                                 {"ply": 4, "san": "d6", "verdict": "blunder", "cp_loss": 300, "best": "Nc6"}]}
        assert game_mode._mistake_text(state["annotations"][0]) == "2.Nf3 (mistake, better d4)"
        assert game_mode._mistake_text(state["annotations"][1]) == "2...d6 (blunder, better Nc6)"
        state.update({"winner": "engine", "termination": "checkmate", "moves": ["e4", "c5", "Nf3", "d6"]})
        assert decisive_moment(state).startswith("Decisive moment: 2...d6 (blunder, better Nc6)")

    def test_the_chat_turn_after_the_game_has_the_same_decisive_line(self):
        """«Разобрать» reads the game block: the same fact as the comment, so the two never disagree."""
        _, board = _testers_game()
        ctx = game_context(board)
        assert "NO decisive mistake" in ctx and "resigning was early" in ctx

    def test_a_resignation_in_a_lost_position_without_one_mistake_says_so(self):
        """No mistake, but the position slipped by small inaccuracies: no «resigning was early» then."""
        state = {"termination": "resign", "winner": "engine", "moves": ["e4"] * 20,
                 "annotations": [{"ply": 19, "san": "h3", "verdict": "inaccuracy", "cp_loss": 60, "eval_after": -320}]}
        moment = decisive_moment(state)
        assert "NO single decisive mistake" in moment and "-3.2" in moment and "early" not in moment


@pytest.mark.unit
class TestTheWords:
    @pytest.mark.parametrize("sentence", [
        TESTER,
        "В предыдущем ответе были приведены ходы, которых в нашей партии не было.",
        "Я ошибся в прошлом ответе, назвав Кf3 третьим ходом.",
        "In my previous answer I named a move that was not played.",
        "No mistakes are listed in the moves given.",
    ])
    def test_talk_about_its_notes_or_its_earlier_answers_is_caught(self, sentence):
        assert is_self_reference(sentence)

    @pytest.mark.parametrize("sentence", [
        "Ты ошибся на 12-м ходу: сильнее было Кf3.", "В прошлой партии ты играл смелее.",
        "Решающей ошибки не было: ты сдался рано.", "Этот ход не указан в книге дебютов.",
        "The previous move was a blunder.", "В последнем ходе ты отдал пешку.",
    ])
    def test_chess_said_plainly_is_not(self, sentence):
        assert not is_self_reference(sentence)

    def test_the_gate_leaves_such_a_sentence_out_and_never_streams_its_start(self):
        """The sentence is held whole while it may be one (its start «В предыдущем » is not released) and dropped."""
        ctx = CheckContext.from_fens([chess.STARTING_FEN], [])
        ctx.language = "ru"
        gate = SentenceGate(ctx, enabled=True, release_starts=True)   # the chat's gate releases claim-free starts
        out = []
        for piece in ("В предыдущем ", "ответе были приведены ходы, ", "которых не было. Сдаваться было рано."):
            out += gate.feed(piece)
        out += gate.flush()
        assert [issues for _, issues, _ in out if issues] == [[SELF_REF_ISSUE]]
        assert "".join(text for text, issues, _ in out if not issues).strip() == "Сдаваться было рано."

    def test_the_chat_is_told_never_to_talk_about_earlier_answers(self):
        """The review after «Разобрать» sees the comment in the history: it states the right fact, never «в
        предыдущем ответе»."""
        assert "Never talk about your own earlier messages" in COACH_SPEECH_LAYER
        assert "do not correct it aloud" in COACH_SPEECH_LAYER
        assert PROMPT_TEMPLATE_VERSION == "22"


@pytest.mark.unit
class TestTheComment:
    def test_the_testers_comment_is_not_shown_and_the_plain_facts_say_it_right(self):
        """The whole comment was the tester's sentence: left out — the fallback says the result and that resigning
        was early."""
        session, board = _testers_game()
        shown = _comment(session, board, TESTER)
        assert "приведённых" not in shown and "не указано" not in shown
        assert shown == "Партия окончена: 0-1. Решающей ошибки не было: сдаваться было рано, партия продолжалась."

    def test_the_right_sentences_of_the_comment_stay(self):
        session, board = _testers_game()
        shown = _comment(session, board, "Ты сдался после 2...d6. " + TESTER + " Хочешь, разберём партию?")
        assert "Хочешь, разберём партию?" in shown and "приведённых" not in shown

    def test_the_plain_facts_in_english_and_kazakh(self):
        _, board = _testers_game()
        assert fallback_comment(board, "en", "end").endswith("resigning was early, the game was still on.")
        assert "Шешуші қате болған жоқ" in fallback_comment(board, "kk", "end")
