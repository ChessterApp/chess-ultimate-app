"""Integration tests for response envelope — full request→envelope flow."""

import json

import chess
import pytest

from src.board_protocol import ActionType
from src.middleware.response_envelope import extract_board_actions, wrap_response


@pytest.mark.integration
class TestEnvelopeIntegration:
    def test_pure_text_response(self):
        """A text-only response produces no board_actions."""
        envelope = wrap_response("The Italian Game starts with 1. e4 e5 2. Nf3 Nc6 3. Bc4.")
        assert envelope["message"] == "The Italian Game starts with 1. e4 e5 2. Nf3 Nc6 3. Bc4."
        assert envelope["board_actions"] == []

    def test_tool_result_extracted(self):
        """Board actions from tool results are extracted into the envelope."""
        tool_result = json.dumps({
            "action": "set_fen",
            "fen": chess.STARTING_FEN,
        })
        envelope = wrap_response(
            "Here's the starting position.",
            tool_results=[tool_result],
        )
        assert envelope["message"] == "Here's the starting position."
        assert len(envelope["board_actions"]) == 1
        assert envelope["board_actions"][0]["action"] == "set_fen"

    def test_embedded_action_extracted_from_text(self):
        """Board actions embedded in text are extracted and text is cleaned."""
        action_json = json.dumps({"action": "flip_board"})
        text = f"Let me flip the board for you. {action_json} There you go."
        envelope = wrap_response(text)
        assert "flip_board" not in envelope["message"]
        assert len(envelope["board_actions"]) == 1
        assert envelope["board_actions"][0]["action"] == "flip_board"

    def test_multiple_sources_combined(self):
        """Board actions from both tool results and text are combined."""
        tool_result = json.dumps({"action": "set_fen", "fen": chess.STARTING_FEN})
        text_with_action = f'Look at this. {json.dumps({"action": "flip_board"})} Done.'
        envelope = wrap_response(text_with_action, tool_results=[tool_result])
        assert len(envelope["board_actions"]) == 2

    def test_non_board_json_ignored(self):
        """JSON objects without a valid action type are left in the text."""
        text = 'The score is {"eval": 1.3, "depth": 20} for this position.'
        envelope = wrap_response(text)
        assert envelope["board_actions"] == []
        assert '{"eval": 1.3, "depth": 20}' in envelope["message"]
