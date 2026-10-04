"""The student's idea on the board: moves in words, the engine's look at them,
and the coach's own recommendation checked before it is shown (2026-10-04)."""

import json
from unittest.mock import MagicMock, patch

import chess
import pytest

from src import config
from src import server
from src.answer_check import CheckContext, proposed_move
from src.hypothetical import hypothetical_notes, moved_piece_facts, verify_recommendation
from src.move_words import prose_moves
from src.prompt_builder import hypothetical_block, moves_in_question_block, question_moves

# Black queen on h4, white knights c3/f3, bishop f1, rooks a1/h1 (the client's
# example of 2026-10-01: «поставь ладью на g1 — она нападает на ферзя h4»).
H4 = "r1b1k1nr/pppp1ppp/2n5/2b1p3/4P2q/2N2N2/PPPP1PPP/R1BQKB1R w KQkq - 0 5"
# The tester's board (2026-10-04): rook d5 and e1, queen c3, black queen h4.
TESTER = "2r2rk1/2p3p1/pp1p1p2/2nR4/P3P2q/1PQ2P1P/2P2PK1/4R3 w - - 0 1"


class TestMovesInWords:
    @pytest.mark.parametrize("text, expect", [
        ("что если поставить ладью на g1?", ["Rg1"]),
        ("а если взять ферзя конём?", ["Nxh4"]),
        ("конём на h4", ["Nxh4"]),
        ("а если я поставлю коня на d5 и потом слона на c4?", ["Nd5", "Bc4"]),
        ("пешку на d4", ["d4"]),
        ("конём бью e5", ["Nxe5"]),
        ("put the rook on g1", ["Rg1"]),
        ("take the queen with the knight", ["Nxh4"]),
        ("knight to d5 and bishop to c4?", ["Nd5", "Bc4"]),
        ("rook takes the queen", []),  # no rook reaches h4: not a legal move
        ("что мне делать?", []),
    ])
    def test_phrases_become_moves(self, text, expect):
        board = chess.Board(H4)
        assert [p["san"] for p in prose_moves(text, board) if p["move"] is not None] == expect

    def test_an_impossible_move_keeps_its_label_for_the_verdict(self):
        board = chess.Board(H4)
        items = prose_moves("ладьёй взять на h4", board)
        assert items and items[0]["move"] is None and items[0]["san"] == "Rxh4"

    def test_ambiguity_is_named(self):
        board = chess.Board("4k3/8/8/8/8/8/4K3/R6R w - - 0 1")  # both rooks reach d1
        items = prose_moves("ладью на d1", board)
        assert items[0]["move"] is None and "more than one rook" in items[0]["note"]

    def test_a_from_square_disambiguates(self):
        board = chess.Board("4k3/8/8/8/8/8/4K3/R6R w - - 0 1")
        items = prose_moves("ладью с a1 на d1", board)
        assert items[0]["san"] == "Rad1" and items[0]["move"] is not None
        assert prose_moves("ладью a1 на d1", board)[0]["san"] == "Rad1"


class TestQuestionMoves:
    def test_notation_and_words_in_one_block(self):
        block = moves_in_question_block("что если поставить ладью на g1? а взять ферзя конём? или Rg1?", H4)
        assert block.startswith("## Moves named in the question")
        assert "- Rg1: legal" in block  # named in notation too: the notation line, once
        assert "- Nxh4 («взять ферзя конем»): legal" in block
        assert block.count("Rg1") == 1  # the same move named twice is one line
        assert "- Rg1 («ладью на g1»): legal" in moves_in_question_block("поставить ладью на g1?", H4)

    def test_a_blocked_capture_in_words_is_explained(self):
        moves = question_moves("ладьёй взять на h4", H4)
        assert moves[0]["legal"] is False
        assert "the pawn on h2 is in the way of the rook on h1" in moves[0]["verdict"]

    def test_legal_moves_carry_the_position_after_them(self):
        moves = question_moves("а если Rg1?", H4)
        after = chess.Board(moves[0]["after_fen"])
        assert after.piece_at(chess.G1).piece_type == chess.ROOK and after.turn == chess.BLACK


def _fake_analysis(scores: dict):
    """analyze_timed stand-in: scores[fen] → (pawns for the side to move, pv)."""
    def _analyze(fen, movetime_ms, multipv=1, min_depth=10):
        score, pv = scores.get(fen, (0.0, ""))
        line = {"multipv": 1, "depth": 12, "pv": pv}
        if isinstance(score, str) and score.startswith("mate"):
            line["mate_in"] = int(score.split()[1])
            line["score"] = 10000 * (1 if line["mate_in"] > 0 else -1)
        else:
            line["score"] = score
        return {"lines": [line]}
    return _analyze


class TestHypotheticalNotes:
    def test_the_rook_on_g1_attacks_nothing_and_the_engine_says_so(self, monkeypatch):
        board = chess.Board(H4)
        after_rg1 = board.copy(stack=False)
        after_rg1.push_san("Rg1")
        after_nxh4 = board.copy(stack=False)
        after_nxh4.push_san("Nxh4")
        scores = {
            H4: (8.6, "f3h4"),                      # White to move: +8.6, best Nxh4
            after_rg1.fen(): ("mate 1", "h4f2"),     # Black to move: mate in 1 for Black
            after_nxh4.fen(): (-8.8, "g8f6"),        # Black to move: -8.8 (so +8.8 for White)
        }
        monkeypatch.setattr("src.hypothetical.analyze_timed", _fake_analysis(scores))
        moves = question_moves("что если поставить ладью на g1? или взять ферзя конём?", H4)
        note = hypothetical_notes(H4, moves, movetime_ms=300)
        text = note["note"]
        assert "- Rg1 («ладью на g1») (White's move)." in text
        assert "the rook on g1 attacks nothing" in text
        assert "it walks into a forced mate" in text and "best reply: Qxf2#" in text
        assert "The engine prefers Nxh4 instead." in text
        assert "- Nxh4 («взять ферзя конем») (White's move)." in text
        assert "a sound move" in text
        assert len(note["fens"]) == 2 and note["fens"][0] == after_rg1.fen()

    def test_a_live_game_keeps_the_engines_own_move_out(self, monkeypatch):
        board = chess.Board(H4)
        after = board.copy(stack=False)
        after.push_san("Rg1")
        monkeypatch.setattr("src.hypothetical.analyze_timed",
                            _fake_analysis({H4: (8.6, "f3h4"), after.fen(): ("mate 1", "h4f2")}))
        note = hypothetical_notes(H4, question_moves("а если Rg1?", H4), movetime_ms=300, reveal_best=False)
        assert "engine prefers" not in note["note"]

    def test_no_legal_move_no_note(self, monkeypatch):
        monkeypatch.setattr("src.hypothetical.analyze_timed", _fake_analysis({}))
        assert hypothetical_notes(H4, question_moves("ладьёй взять на h4", H4)) is None

    def test_without_an_engine_the_board_facts_still_come(self, monkeypatch):
        monkeypatch.setattr("src.hypothetical.analyze_timed", lambda *a, **k: {"error": "Stockfish not found"})
        note = hypothetical_notes(H4, question_moves("а если Rg1?", H4))
        assert "the rook on g1 attacks nothing" in note["note"] and "Evaluation" not in note["note"]

    def test_moved_piece_facts_name_attacks_and_safety(self):
        board = chess.Board(TESTER)
        move = board.parse_san("Rg1")
        after = board.copy(stack=False)
        after.push(move)
        facts = moved_piece_facts(board, after, move)
        assert facts[0] == "the rook on g1 attacks nothing"
        assert "the rook on g1 is not attacked" in facts

    def test_the_block_tells_the_model_how_to_use_it(self):
        block = hypothetical_block("- Rg1 …", live_game=False)
        assert block.startswith("## The student's idea, played on the board (engine)")
        assert "never from memory" in block
        live = hypothetical_block("- Rg1 …", live_game=True)
        assert "do not name a better move for the student" in live


class TestProposedMove:
    @pytest.mark.parametrize("sentence, expect", [
        ("Сыграй Rg1 — ладья уходит из-под удара.", "Rg1"),
        ("Лучше всего здесь Nd5.", "Nd5"),
        ("Можно поставить ладью на g1.", "Rg1"),
        ("Я бы сыграл Nxh4 — забираем ферзя.", "Nxh4"),
        ("Play Nd5 and the knight dominates.", "Nd5"),
        ("You should put the rook on g1.", "Rg1"),
        ("Хороший ход — d4.", "d4"),
        ("Сыграй пешкой на d4.", "d4"),
        ("Берём ферзя: Nxh4!", "Nxh4"),
        ("Лучше 1.Nd5, с угрозой Nxc7+.", "Nd5"),
        ("Лучше Nd5, чем Rg1.", "Nd5"),
        ("Ход Nd5 — как раз самый сильный: конь идёт в центр.", "Nd5"),
        ("Nxh4 is the best move here.", "Nxh4"),
    ])
    def test_a_recommendation_is_found(self, sentence, expect):
        ctx = CheckContext.from_fens([H4], question="что делать?")
        found = proposed_move(sentence, ctx)
        assert found is not None and found[2] == expect, (sentence, found)

    @pytest.mark.parametrize("sentence", [
        "Не стоит играть Rg1.",
        "Rg1 сыграть нельзя — пешка мешает.",
        "Если сыграть Rg1, ладья нападает на ферзя h4.",  # a hypothetical, not advice
        "Можно заметить, что после Rg1 ладья стоит плохо.",
        "Отличная позиция, можно спокойно развиваться.",
        "Ход Rg1 — ошибка: ладья ничего не атакует.",  # named, judged bad: not a recommendation
        "Лучше ...Nf6, чем ...Qh4.",  # Black's move on White's turn: not for the side to move
    ])
    def test_no_recommendation(self, sentence):
        ctx = CheckContext.from_fens([H4], question="что делать?")
        assert proposed_move(sentence, ctx) is None, sentence

    def test_a_square_named_after_a_piece_is_not_a_pawn_move(self):
        # The tester's board has no white knight: 3.Nxe5 is for another board, and
        # «пешка e5» names a square (the stand's second-board test, 2026-10-04).
        ctx = CheckContext.from_fens([TESTER], question="а на второй доске?")
        assert proposed_move("На второй доске бери 3.Nxe5 — пешка e5 висит.", ctx) is None

    def test_without_a_board_nothing_is_checked(self):
        assert proposed_move("Сыграй Nf3.", CheckContext.from_fens()) is None


class TestVerifyRecommendation:
    def test_a_blunder_is_named_with_the_reply_and_the_facts(self, monkeypatch):
        board = chess.Board(H4)
        move = board.parse_san("Rg1")
        after = board.copy(stack=False)
        after.push(move)
        monkeypatch.setattr("src.hypothetical.analyze_timed",
                            _fake_analysis({H4: (8.6, "f3h4"), after.fen(): ("mate 1", "h4f2")}))
        why = verify_recommendation(board, move, "Rg1", threshold_cp=150)
        assert why.startswith("Rg1 is a blunder on this board (engine): it walks into a forced mate — Rg1 Qxf2#")
        assert "the rook on g1 attacks nothing" in why
        assert "The engine's move here is Nxh4" in why
        assert "engine's move" not in verify_recommendation(board, move, "Rg1", threshold_cp=150, reveal_best=False)

    def test_a_sound_move_passes(self, monkeypatch):
        board = chess.Board(H4)
        move = board.parse_san("Nxh4")
        after = board.copy(stack=False)
        after.push(move)
        monkeypatch.setattr("src.hypothetical.analyze_timed",
                            _fake_analysis({H4: (8.6, "f3h4"), after.fen(): (-8.8, "g8f6")}))
        assert verify_recommendation(board, move, "Nxh4") is None

    def test_a_small_loss_is_under_the_threshold(self, monkeypatch):
        board = chess.Board(H4)
        move = board.parse_san("Nd5")
        after = board.copy(stack=False)
        after.push(move)
        monkeypatch.setattr("src.hypothetical.analyze_timed",
                            _fake_analysis({H4: (0.5, "f3h4"), after.fen(): (0.9, "g8f6")}))  # −0.9 for White after: 1.4 pawns
        assert verify_recommendation(board, move, "Nd5", threshold_cp=150) is None
        assert verify_recommendation(board, move, "Nd5", threshold_cp=100) is not None

    def test_the_engine_being_away_is_not_an_issue(self, monkeypatch):
        board = chess.Board(H4)
        monkeypatch.setattr("src.hypothetical.analyze_timed", lambda *a, **k: {"error": "no engine"})
        assert verify_recommendation(board, board.parse_san("Rg1"), "Rg1") is None


def _turn(monkeypatch, answer: str, message: str, fen: str, **flags):
    """One chat turn with a mocked agent streaming *answer*; returns (message the model got, SSE frames)."""
    from fastapi.testclient import TestClient

    from src.sessions import session_store
    from src.user_profile import UserProfile

    session = session_store.create(user_id="idea-user")
    board = session.ensure_board()
    session.set_board_state(fen, board_id=board.id)
    agent = MagicMock()
    agent.tools = []
    agent._api_call_count = 1
    agent.max_iterations = 5
    agent.session_prompt_tokens = agent.session_completion_tokens = 0
    captured = {}

    def _chat(msg, stream_callback=None):
        captured["message"] = msg
        for i in range(0, len(answer), 7):
            stream_callback(answer[i:i + 7])
        return answer

    agent.chat.side_effect = _chat
    monkeypatch.setattr(config, "COACH_TWO_STAGE", False)
    monkeypatch.setattr(config, "COACH_ENGINE_NOTE", False)
    monkeypatch.setattr(config, "COACH_ANSWER_CHECK", True)
    monkeypatch.setattr(config, "COACH_HYPOTHETICAL_NOTE", True)
    monkeypatch.setattr(config, "COACH_MOVE_VERIFY", True)
    for name, value in flags.items():
        monkeypatch.setattr(config, name, value)
    with patch("src.server._create_agent", return_value=agent), \
            patch("src.server.load_user_profile", return_value=UserProfile(user_id="idea-user")), \
            patch("src.server.log_event"):
        resp = TestClient(server.app).post(
            "/api/coach/chat", headers={"X-User-Id": "idea-user"},
            json={"message": message, "session_id": session.id, "locale": "ru", "fen": fen},
        )
    assert resp.status_code == 200
    frames = [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: ")]
    return captured.get("message", ""), frames


@pytest.mark.unit
def test_the_students_idea_reaches_the_model_with_the_engines_facts(monkeypatch):
    board = chess.Board(H4)
    after = board.copy(stack=False)
    after.push_san("Rg1")
    monkeypatch.setattr("src.hypothetical.analyze_timed",
                        _fake_analysis({H4: (8.6, "f3h4"), after.fen(): ("mate 1", "h4f2")}))
    message, _ = _turn(monkeypatch, "Смотри на доску.", "а что если поставить ладью на g1?", H4,
                       COACH_MOVE_VERIFY=False)
    assert "## Moves named in the question" in message and "- Rg1 («ладью на g1»): legal" in message
    assert "## The student's idea, played on the board (engine)" in message
    assert "the rook on g1 attacks nothing" in message and "best reply: Qxf2#" in message


@pytest.mark.unit
def test_the_idea_block_can_be_switched_off(monkeypatch):
    monkeypatch.setattr("src.hypothetical.analyze_timed", _fake_analysis({}))
    message, _ = _turn(monkeypatch, "Смотри на доску.", "а что если Rg1?", H4,
                       COACH_HYPOTHETICAL_NOTE=False, COACH_MOVE_VERIFY=False)
    assert "## Moves named in the question" in message
    assert "played on the board (engine)" not in message


@pytest.mark.unit
def test_a_recommended_blunder_is_not_shown(monkeypatch):
    board = chess.Board(H4)
    after = board.copy(stack=False)
    after.push_san("Rg1")
    monkeypatch.setattr("src.hypothetical.analyze_timed",
                        _fake_analysis({H4: (8.6, "f3h4"), after.fen(): ("mate 1", "h4f2")}))
    answer = "Позиция острая. Сыграй Rg1 — ладья уходит из-под удара и давит на g7. Потом можно думать о рокировке."
    _, frames = _turn(monkeypatch, answer, "что мне играть?", H4, COACH_ANSWER_FIX=False)
    text = "".join(f.get("delta", "") for f in frames)
    assert "Позиция острая." in text
    assert "Сыграй Rg1" not in text and "давит на g7" not in text
    assert "рокировке" in text  # the rest of the draft goes on (no rewrite with the fix off)


@pytest.mark.unit
def test_a_sound_recommendation_streams(monkeypatch):
    board = chess.Board(H4)
    after = board.copy(stack=False)
    after.push_san("Nxh4")
    monkeypatch.setattr("src.hypothetical.analyze_timed",
                        _fake_analysis({H4: (8.6, "f3h4"), after.fen(): (-8.8, "g8f6")}))
    answer = "Просто бери ферзя: Nxh4! Это выигрывает партию."
    _, frames = _turn(monkeypatch, answer, "что мне играть?", H4, COACH_ANSWER_FIX=False)
    text = "".join(f.get("delta", "") for f in frames)
    assert "Nxh4" in text and "выигрывает" in text
