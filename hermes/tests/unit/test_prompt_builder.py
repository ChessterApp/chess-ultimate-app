"""Unit tests for system prompt builder."""

import httpx
import chess
import pytest

import src.prompt_builder as prompt_builder
from src.prompt_builder import build_system_prompt, LOCALE_TO_LANGUAGE
from src.user_profile import UserProfile

MOCK_SOUL = "# Chess Coach\nYou are a chess coach."

CCP_BLOCK = "<detailed_board_analysis>MASTRA CCP fusion here</detailed_board_analysis>"
LOCAL_BLOCK = "LOCAL PYTHON PORT ANALYSIS"


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _isolate_analysis_cache():
    """Keep the module-global FEN analysis cache from leaking across tests."""
    prompt_builder.clear_analysis_cache()
    yield
    prompt_builder.clear_analysis_cache()


@pytest.mark.unit
class TestPromptBuilder:
    def test_soul_only(self):
        prompt = build_system_prompt(soul_content=MOCK_SOUL)
        assert "Chess Coach" in prompt
        assert "Student Profile" not in prompt
        assert "Board Control" in prompt

    def test_with_user_profile(self):
        profile = UserProfile(
            user_id="u1",
            rating=1500,
            goals=["Improve tactics"],
            weaknesses=["Endgames"],
        )
        prompt = build_system_prompt(
            soul_content=MOCK_SOUL,
            user_profile=profile,
        )
        assert "Student Profile" in prompt
        assert "1500" in prompt
        assert "Improve tactics" in prompt
        assert "Endgames" in prompt

    def test_with_board_state(self):
        prompt = build_system_prompt(
            soul_content=MOCK_SOUL,
            board_fen=chess.STARTING_FEN,
        )
        assert "Current Board State" in prompt
        assert chess.STARTING_FEN in prompt

    def test_with_move_history(self):
        prompt = build_system_prompt(
            soul_content=MOCK_SOUL,
            board_fen=chess.STARTING_FEN,
            move_history=["e4", "e5", "Nf3", "Nc6"],
        )
        assert "Move history" in prompt
        assert "1. e4 e5" in prompt
        assert "2. Nf3 Nc6" in prompt

    def test_combines_all_sources(self):
        profile = UserProfile(user_id="u1", rating=2000, style="aggressive")
        prompt = build_system_prompt(
            soul_content=MOCK_SOUL,
            user_profile=profile,
            board_fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
            move_history=["e4"],
        )
        assert "Chess Coach" in prompt
        assert "Student Profile" in prompt
        assert "2000" in prompt
        assert "aggressive" in prompt
        assert "Current Board State" in prompt
        assert "Board Control" in prompt

    def test_locale_russian_injects_directive(self):
        prompt = build_system_prompt(soul_content=MOCK_SOUL, locale="ru")
        assert "CRITICAL LANGUAGE RULE" in prompt
        assert "Russian" in prompt
        # Language directive must come before SOUL content
        lang_pos = prompt.index("CRITICAL LANGUAGE RULE")
        soul_pos = prompt.index("Chess Coach")
        assert lang_pos < soul_pos

    def test_locale_kazakh_injects_directive(self):
        prompt = build_system_prompt(soul_content=MOCK_SOUL, locale="kz")
        assert "CRITICAL LANGUAGE RULE" in prompt
        assert "Kazakh" in prompt

    def test_locale_english_no_directive(self):
        prompt = build_system_prompt(soul_content=MOCK_SOUL, locale="en")
        assert "CRITICAL LANGUAGE RULE" not in prompt

    def test_locale_none_no_directive(self):
        prompt = build_system_prompt(soul_content=MOCK_SOUL, locale=None)
        assert "CRITICAL LANGUAGE RULE" not in prompt

    def test_locale_unknown_uses_code(self):
        prompt = build_system_prompt(soul_content=MOCK_SOUL, locale="fr")
        assert "CRITICAL LANGUAGE RULE" in prompt
        assert "fr" in prompt

    def test_locale_to_language_mapping(self):
        assert LOCALE_TO_LANGUAGE["ru"] == "Russian"
        assert LOCALE_TO_LANGUAGE["kz"] == "Kazakh"
        assert LOCALE_TO_LANGUAGE["en"] == "English"

    def test_prompt_contains_set_fen_example(self):
        prompt = build_system_prompt(soul_content=MOCK_SOUL)
        assert "set_fen" in prompt
        assert "draw_arrows" in prompt
        assert "Scholar's Mate" in prompt

    def test_prompt_contains_example_fen(self):
        prompt = build_system_prompt(soul_content=MOCK_SOUL)
        assert "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4" in prompt

    def test_prompt_contains_check_moves_directive(self):
        # Text mode must instruct verifying non-engine move suggestions.
        prompt = build_system_prompt(soul_content=MOCK_SOUL)
        assert "check_moves" in prompt


@pytest.mark.unit
class TestCacheAlignedOrdering:
    """Static blocks (persona + tool usage) must precede volatile ones.

    The current date, student profile, and board/FEN change turn-to-turn, so
    they trail the static prefix to keep the Anthropic prompt-cache prefix hot.
    """

    FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"

    def test_static_tool_block_precedes_current_date(self):
        profile = UserProfile(user_id="u1", rating=1500)
        prompt = build_system_prompt(
            soul_content=MOCK_SOUL, user_profile=profile, board_fen=self.FEN
        )
        assert prompt.index("Tool Usage (MANDATORY)") < prompt.index("## Current Date")

    def test_static_prefix_precedes_all_volatile_markers(self):
        profile = UserProfile(user_id="u1", rating=1500, goals=["Improve tactics"])
        prompt = build_system_prompt(
            soul_content=MOCK_SOUL, user_profile=profile, board_fen=self.FEN
        )
        # The whole static prefix (persona + tool block) is ahead of every
        # volatile marker: current date, student profile, and the FEN.
        static_end = prompt.index("Tool Usage (MANDATORY)")
        for volatile in ("## Current Date", "## Student Profile", self.FEN):
            assert static_end < prompt.index(volatile), volatile
        # Persona still leads the static prefix.
        assert prompt.index("Chess Coach") < static_end

    def test_all_sections_still_present_after_reorder(self):
        """Regression: reordering must not drop any section."""
        profile = UserProfile(user_id="u1", rating=1800, goals=["Endgames"])
        prompt = build_system_prompt(
            soul_content=MOCK_SOUL,
            user_profile=profile,
            board_fen=self.FEN,
            move_history=["e4", "e5"],
            locale="ru",
        )
        for marker in (
            "CRITICAL LANGUAGE RULE",
            "Chess Coach",
            "Tool Usage (MANDATORY)",
            "Board Control",
            "## Current Date",
            "## Student Profile",
            "## Current Board State",
            self.FEN,
            "Move history",
        ):
            assert marker in prompt, marker


@pytest.mark.unit
class TestCcpAnalysisInjection:
    """Board analysis prefers the Mastra CCP service, falls back to local port."""

    def test_ccp_service_success_uses_mastra_block(self, monkeypatch):
        # CCP returns a valid analysis -> Mastra block appears...
        def fake_post(url, json=None, timeout=None):
            return _FakeResponse(200, {"valid": True, "board_analysis": CCP_BLOCK})

        monkeypatch.setattr(httpx, "post", fake_post)

        # ...and the local port must NOT be consulted.
        def boom(fen):
            raise AssertionError("local build_board_analysis must not be called")

        import src.tools.tactical_board as tactical_board
        monkeypatch.setattr(tactical_board, "build_board_analysis", boom)

        prompt = build_system_prompt(
            soul_content=MOCK_SOUL, board_fen=chess.STARTING_FEN
        )
        assert CCP_BLOCK in prompt

    def test_ccp_failure_falls_back_to_local_port(self, monkeypatch):
        # CCP raises (timeout/connection/non-200) -> fall back to local port.
        def fake_post(url, json=None, timeout=None):
            raise httpx.ConnectError("boom")

        monkeypatch.setattr(httpx, "post", fake_post)

        import src.tools.tactical_board as tactical_board
        monkeypatch.setattr(
            tactical_board, "build_board_analysis", lambda fen: LOCAL_BLOCK
        )

        prompt = build_system_prompt(
            soul_content=MOCK_SOUL, board_fen=chess.STARTING_FEN
        )
        assert LOCAL_BLOCK in prompt
        assert CCP_BLOCK not in prompt

    def test_ccp_non200_falls_back_to_local_port(self, monkeypatch):
        monkeypatch.setattr(
            httpx, "post", lambda *a, **k: _FakeResponse(503, {"error": "down"})
        )
        import src.tools.tactical_board as tactical_board
        monkeypatch.setattr(
            tactical_board, "build_board_analysis", lambda fen: LOCAL_BLOCK
        )
        prompt = build_system_prompt(
            soul_content=MOCK_SOUL, board_fen=chess.STARTING_FEN
        )
        assert LOCAL_BLOCK in prompt

    def test_both_paths_failing_does_not_raise(self, monkeypatch):
        # Invalid FEN with both paths failing -> build_prompt returns cleanly.
        def fake_post(url, json=None, timeout=None):
            raise httpx.ConnectError("boom")

        monkeypatch.setattr(httpx, "post", fake_post)

        import src.tools.tactical_board as tactical_board

        def boom(fen):
            raise ValueError("bad fen")

        monkeypatch.setattr(tactical_board, "build_board_analysis", boom)

        prompt = build_system_prompt(
            soul_content=MOCK_SOUL, board_fen="not-a-valid-fen"
        )
        assert "Chess Coach" in prompt

    def test_fetch_ccp_analysis_helper_returns_none_on_invalid_body(self, monkeypatch):
        monkeypatch.setattr(
            httpx, "post", lambda *a, **k: _FakeResponse(200, {"valid": False, "board_analysis": ""})
        )
        assert prompt_builder._fetch_ccp_analysis(chess.STARTING_FEN) is None


@pytest.mark.unit
class TestAnalysisCache:
    """FEN-keyed board-analysis cache skips a repeat fetch for the same FEN."""

    FEN_A = chess.STARTING_FEN
    FEN_B = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"

    def _counting_fetch(self, monkeypatch, result):
        calls = {"n": 0}

        def fake_fetch(fen):
            calls["n"] += 1
            return result

        monkeypatch.setattr(prompt_builder, "_fetch_ccp_analysis", fake_fetch)
        return calls

    def test_identical_fen_fetched_once(self, monkeypatch):
        calls = self._counting_fetch(monkeypatch, CCP_BLOCK)
        first = build_system_prompt(soul_content=MOCK_SOUL, board_fen=self.FEN_A)
        second = build_system_prompt(soul_content=MOCK_SOUL, board_fen=self.FEN_A)
        assert CCP_BLOCK in first
        assert CCP_BLOCK in second
        assert calls["n"] == 1

    def test_different_fens_each_fetched(self, monkeypatch):
        calls = self._counting_fetch(monkeypatch, CCP_BLOCK)
        build_system_prompt(soul_content=MOCK_SOUL, board_fen=self.FEN_A)
        build_system_prompt(soul_content=MOCK_SOUL, board_fen=self.FEN_B)
        assert calls["n"] == 2

    def test_failed_lookup_is_not_cached(self, monkeypatch):
        # CCP returns None and local port also returns None -> nothing cached,
        # so the next turn retries the fetch instead of serving a stale miss.
        calls = self._counting_fetch(monkeypatch, None)
        import src.tools.tactical_board as tactical_board
        monkeypatch.setattr(tactical_board, "build_board_analysis", lambda fen: None)
        build_system_prompt(soul_content=MOCK_SOUL, board_fen=self.FEN_A)
        build_system_prompt(soul_content=MOCK_SOUL, board_fen=self.FEN_A)
        assert calls["n"] == 2

    def test_resolve_returns_cached_block_without_second_fetch(self, monkeypatch):
        calls = self._counting_fetch(monkeypatch, CCP_BLOCK)
        assert prompt_builder._resolve_board_analysis(self.FEN_A) == CCP_BLOCK
        assert prompt_builder._resolve_board_analysis(self.FEN_A) == CCP_BLOCK
        assert calls["n"] == 1

    def test_invalid_fen_does_not_crash_and_is_not_cached(self, monkeypatch):
        # Both paths raise -> resolve surfaces cleanly and caches nothing.
        def boom_fetch(fen):
            raise RuntimeError("ccp down")

        monkeypatch.setattr(prompt_builder, "_fetch_ccp_analysis", boom_fetch)
        import src.tools.tactical_board as tactical_board

        def boom_local(fen):
            raise ValueError("bad fen")

        monkeypatch.setattr(tactical_board, "build_board_analysis", boom_local)
        prompt = build_system_prompt(soul_content=MOCK_SOUL, board_fen="not-a-fen")
        assert "Chess Coach" in prompt
        assert len(prompt_builder._analysis_cache) == 0


@pytest.mark.unit
class TestBuildVoicePrompt:
    """Task 2/3: single-source spoken prompt (SOUL persona + spoken layer +
    profile), so voice and text can't drift."""

    def test_includes_persona_and_spoken_style(self):
        prompt = prompt_builder.build_voice_prompt(MOCK_SOUL)
        assert "You are a chess coach." in prompt  # SOUL persona core
        assert "Speaking Style (voice mode)" in prompt
        assert "NO markdown" in prompt
        # Speak-before-tool-call directive is preserved.
        assert "acknowledgment" in prompt.lower()

    def test_includes_profile_context(self):
        profile = UserProfile(
            user_id="u1", rating=1750, weaknesses=["time pressure"], goals=["reach 1800"]
        )
        prompt = prompt_builder.build_voice_prompt(MOCK_SOUL, user_profile=profile)
        assert "Student rating: 1750" in prompt
        assert "time pressure" in prompt

    def test_includes_fen_anchor(self):
        fen = "8/8/8/8/8/8/8/K6k w - - 0 1"
        prompt = prompt_builder.build_voice_prompt(MOCK_SOUL, board_fen=fen)
        assert fen in prompt

    def test_language_directive_for_non_english(self):
        prompt = prompt_builder.build_voice_prompt(MOCK_SOUL, locale="ru")
        assert "Russian" in prompt

    def test_no_language_directive_for_english(self):
        prompt = prompt_builder.build_voice_prompt(MOCK_SOUL, locale="en")
        assert "MUST respond entirely in" not in prompt

    def test_tools_toggle(self):
        with_tools = prompt_builder.build_voice_prompt(MOCK_SOUL, tools_available=True)
        without = prompt_builder.build_voice_prompt(MOCK_SOUL, tools_available=False)
        assert "Tools (voice mode)" in with_tools
        assert "Tools (voice mode)" not in without

    def test_includes_check_moves_directive(self):
        # Voice mode must verify a spoken non-engine move with check_moves.
        prompt = prompt_builder.build_voice_prompt(MOCK_SOUL, tools_available=True)
        assert "check_moves" in prompt
        # And it belongs to the tool layer, not present when tools are off.
        without = prompt_builder.build_voice_prompt(MOCK_SOUL, tools_available=False)
        assert "check_moves" not in without

    def test_no_markdown_headings_leak_into_spoken_body(self):
        # The spoken prompt must not inject the heavy tactical-analysis block the
        # text path adds (kept lean for low-latency minting).
        prompt = prompt_builder.build_voice_prompt(
            MOCK_SOUL, board_fen="8/8/8/8/8/8/8/K6k w - - 0 1"
        )
        assert "detailed_board_analysis" not in prompt
