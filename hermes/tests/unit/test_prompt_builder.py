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

    def test_locale_english_gets_the_same_rule(self):
        # The question's language wins for every interface language, English too.
        prompt = build_system_prompt(soul_content=MOCK_SOUL, locale="en")
        assert "CRITICAL LANGUAGE RULE" in prompt
        assert "The interface language is English" in prompt

    def test_question_language_beats_interface_language(self):
        prompt = build_system_prompt(soul_content=MOCK_SOUL, locale="ru")
        assert "language of the student's latest message" in prompt
        assert "even when it differs from the" in prompt
        assert "respond entirely in" not in prompt

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

    def test_prompt_sends_concept_examples_to_the_tools(self):
        # 2026-09-25: the coach typed its own "pin" position (a knight on c3 that
        # wasn't there). Examples now come from get_topic / get_lesson only.
        prompt = build_system_prompt(soul_content=MOCK_SOUL)
        assert "set_fen" in prompt
        assert "[[arrows:" in prompt  # arrows are inline marks since 2026-09-27
        assert "call get_topic FIRST" in prompt
        assert "Never type an example" in prompt
        assert "Construct clear example positions" not in prompt

    def test_prompt_has_no_hand_written_example_fen(self):
        prompt = build_system_prompt(soul_content=MOCK_SOUL)
        assert "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4" not in prompt
        assert "Scholar's Mate" not in prompt

    def test_voice_prompt_forbids_invented_examples(self):
        from src.prompt_builder import build_voice_prompt
        prompt = build_voice_prompt(MOCK_SOUL)
        assert "come ONLY from get_topic or get_lesson" in prompt

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

    def test_timeout_skips_the_service_for_a_while(self, monkeypatch):
        monkeypatch.setattr(prompt_builder, "_ccp_skip_until", 0.0)
        calls = {"n": 0}

        def slow_post(*a, **k):
            calls["n"] += 1
            raise httpx.ReadTimeout("slow")

        monkeypatch.setattr(httpx, "post", slow_post)
        assert prompt_builder._fetch_ccp_analysis(chess.STARTING_FEN) is None
        assert prompt_builder._fetch_ccp_analysis(chess.STARTING_FEN) is None
        assert calls["n"] == 1

    def test_connection_error_does_not_back_off(self, monkeypatch):
        monkeypatch.setattr(prompt_builder, "_ccp_skip_until", 0.0)
        calls = {"n": 0}

        def refused(*a, **k):
            calls["n"] += 1
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(httpx, "post", refused)
        prompt_builder._fetch_ccp_analysis(chess.STARTING_FEN)
        prompt_builder._fetch_ccp_analysis(chess.STARTING_FEN)
        assert calls["n"] == 2


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

    def test_voice_uses_the_same_language_rule_as_text(self):
        prompt = prompt_builder.build_voice_prompt(MOCK_SOUL, locale="kz")
        assert prompt.startswith(prompt_builder.language_rule("kz"))
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


# ── The language the student asks for (2026-10-01) ─────────────────────────
#
# The tester asked the coach, in the middle of a game, to speak Russian; the
# chat answered in the language of each message and the move comments in the
# interface language, so the request was "refused". A request now holds for
# the session and every surface (answer, reaction, comments) uses one choice.


@pytest.mark.unit
@pytest.mark.parametrize("message, code", [
    ("говори по-русски", "ru"), ("Говори по русски пожалуйста", "ru"), ("отвечай на русском", "ru"),
    ("давай на русском", "ru"), ("можно по-русски?", "ru"), ("перейди на русский", "ru"),
    ("только по-русски, пожалуйста", "ru"), ("смени язык на русский", "ru"), ("язык: русский", "ru"),
    ("speak Russian", "ru"), ("please answer in Russian", "ru"), ("Russian please", "ru"),
    ("switch to Russian", "ru"), ("Can you speak Russian?", "ru"), ("I prefer Russian", "ru"),
    ("орысша сөйле", "ru"), ("no, speak Russian", "ru"),
    ("давай по-английски", "en"), ("answer in English", "en"), ("переходи на английский", "en"),
    ("ағылшынша жауап бер", "en"), ("Please don't speak English, speak Russian", "ru"),
    ("хватит по-английски, говори по-русски", "ru"),
    ("қазақша сөйле", "kk"), ("говори по-казахски", "kk"), ("answer in Kazakh please", "kk"),
    ("қазақша жауап беріңізші", "kk"),
])
def test_a_request_for_a_language_is_recognised(message, code):
    from src.prompt_builder import language_request

    assert language_request(message) == code


@pytest.mark.unit
@pytest.mark.parametrize("message", [
    # a language named for a word or a translation, not for a switch
    "как по-английски будет вилка?", "как это называется по-русски?", "How do you say fork in Russian?",
    "What's the Russian word for fork?", "what does вилка mean in English?", "переведи на русский",
    # an opening, a player
    "расскажи про английское начало", "explain the English Opening", "русский шахматист Карпов",
    # negated
    "не говори по-английски", "don't speak English", "не надо по-английски", "not in English please",
    "no English please", "stop speaking English", "никогда не отвечай по-английски",
    # no language named
    "I still don't get it. So if instead of b3 I played Rg1?", "Что играть дальше?", "Nf3?", "ты понимаешь по-русски?",
])
def test_a_mention_of_a_language_is_not_a_request(message):
    from src.prompt_builder import language_request

    assert language_request(message) is None


@pytest.mark.unit
def test_the_session_language_is_what_was_asked_else_written_else_the_interface():
    from src.prompt_builder import conversation_language, language_note, reply_language_note

    # Newest first. A request anywhere in the session wins, however the later messages are written.
    assert conversation_language(["Nf3?", "What should I play?", "говори по-русски"], "en") == ("ru", "asked")
    assert conversation_language(["Что играть?", "answer in English please"], "ru") == ("en", "asked")
    # The most recent request wins over an older one.
    assert conversation_language(["давай по-английски", "говори по-русски"], "ru") == ("en", "asked")
    # Without a request: the language the student writes in — a move carries none,
    # so the latest message with a language decides, not the interface.
    assert conversation_language(["What should I play?"], "ru") == ("en", "message")
    assert conversation_language(["Nf3?", "What should I play?"], "ru") == ("en", "message")
    assert conversation_language(["Осы жерде не жүру керек?"], "ru") == ("kk", "message")
    # Nothing written in a language: the interface locale.
    assert conversation_language(["Nf3?"], "kz") == ("kz", "interface")
    assert conversation_language([], "en") == ("en", "interface")
    assert conversation_language([], None) == ("ru", "interface")
    # The note the turn ends with says why, so the model does not "correct" it.
    assert reply_language_note("ok", "en", ["говори по-русски"]).startswith(
        "[Reply language: write your whole answer in Russian — the language the student asked for")
    assert "the language of the student's message" in reply_language_note("What now?", "ru")
    assert "the student's interface language" in language_note("kz", "interface")
    assert language_note("ru", "interface").endswith("Never switch to another language.]")
    assert language_note("kz", "interface").endswith("]")  # the Kazakh note carries the chess terms after the rule


@pytest.mark.unit
def test_the_language_rule_tells_the_model_to_honour_a_request():
    from src import prompt_builder

    rule = prompt_builder.language_rule("ru")
    assert "The interface language is Russian" in rule
    assert "asks you to speak a particular language" in rule
    assert prompt_builder.LOCALE_TO_LANGUAGE["kk"] == "Kazakh"


@pytest.mark.unit
def test_the_voice_prompt_carries_the_session_language():
    from src import prompt_builder

    base = prompt_builder.build_voice_prompt("SOUL", locale="en")
    asked = prompt_builder.build_voice_prompt("SOUL", locale="en", language=("ru", "asked"))
    written = prompt_builder.build_voice_prompt("SOUL", locale="en", language=("kk", "message"))
    interface = prompt_builder.build_voice_prompt("SOUL", locale="en", language=("en", "interface"))
    assert asked.startswith(prompt_builder.language_rule("en") + " The student has asked you to speak Russian")
    assert "until they ask otherwise" in asked
    # Only used, not asked: the spoken question decides — a mention of Kazakh made the
    # voice answer a Russian question in Kazakh (production 2026-10-07).
    assert "The conversation so far has been in" not in written
    assert interface == base
    assert prompt_builder.spoken_language_note("en", "interface") == ""


# ── More ways to ask, languages the coach does not speak, scripts (2026-10-02) ──


@pytest.mark.unit
@pytest.mark.parametrize("message, code", [
    ("вернись на русский", "ru"), ("обратно на русский", "ru"), ("вернёмся к русскому", "ru"),
    ("а теперь казахский", "kk"), ("по-русски!", "ru"), ("RU please", "ru"), ("рус", "ru"), ("eng", "en"),
    ("english only from now on", "en"), ("Давай дальше по-английски, мне надо практиковаться", "en"),
    # a question in the same message does not cancel the request (stand, 2026-10-04)
    ("Please answer in Russian: what is a skewer?", "ru"), ("Отвечай по-английски: что такое связка?", "en"),
    ("Can you explain in Russian what a pin is?", "ru"),
])
def test_more_ways_to_ask_for_a_language(message, code):
    from src.prompt_builder import language_request

    assert language_request(message) == code


@pytest.mark.unit
def test_a_language_the_coach_does_not_speak_is_noticed_not_followed():
    from src.prompt_builder import conversation_language, language_note, language_request, other_language_request, \
        spoken_language_note

    assert language_request("говори по-немецки") is None
    assert other_language_request("говори по-немецки") == "German"
    assert other_language_request("speak Spanish please") == "Spanish"
    assert other_language_request("как по-немецки будет вилка?") is None
    assert other_language_request("не говори по-немецки") is None
    assert conversation_language(["говори по-немецки"], "ru") == ("ru", "unsupported:German")
    assert conversation_language(["speak German please", "что играть?"], "ru") == ("en", "unsupported:German")
    # Only the message of this turn: an old request does not repeat the apology.
    assert conversation_language(["Nf3?", "speak German"], "ru") == ("en", "message")
    note = language_note("ru", "unsupported:German")
    assert "asked you to speak German, which you do not speak" in note and "write the whole answer in Russian" in note
    assert "German" in spoken_language_note("ru", "unsupported:German")


@pytest.mark.unit
@pytest.mark.parametrize("message, code", [
    ("Explain Сицилианская защита please", "en"),   # English with a Russian name in it
    ("what is 'вилка' in chess?", "en"),
    ("Что мне играть против Sicilian?", "ru"),
    ("спасибо, thanks!", "ru"),                      # a tie goes to the first word
    ("Мен не ойнауым керек?", "kk"),                 # Kazakh spelt with Russian letters only
    ("Осында не істеу керек?", "kk"),
    ("Ok", None), ("👍", None), ("Nf3?", None), ("1. e4 e5 2. Nf3 Nc6", None),
])
def test_the_script_of_a_message(message, code):
    from src.prompt_builder import _script_language

    assert _script_language(message) == code


@pytest.mark.unit
def test_the_prompt_sends_the_student_to_the_sites_lesson():
    from src import prompt_builder

    prompt = prompt_builder.build_system_prompt(soul_content="SOUL", locale="ru")
    text = prompt if isinstance(prompt, str) else prompt[0]
    assert "the site's own lessons are the student's programme and come FIRST" in text
    assert "END the answer by inviting the student to go through that lesson" in text
    voice = prompt_builder.build_voice_prompt("SOUL", locale="ru")
    assert "send the student to that lesson's tasks at the end" in voice


@pytest.mark.unit
def test_moves_named_in_the_question_are_checked_before_the_answer():
    from src.prompt_builder import moves_in_question_block

    fen = "2r2rk1/2p3p1/pp1p1p2/2nR4/P3P2q/1PQ2P1P/2P2PK1/4R3 w - - 0 1"
    block = moves_in_question_block("Могу ли я сыграть Rg1 сейчас? А Qxg7? А Лd8?", fen)
    assert block.startswith("## Moves named in the question")
    assert "- Rg1: legal" in block
    assert "- Qxg7: NOT legal — the pawn on f6 is in the way of the queen on c3" in block
    assert "- Rd8: NOT legal — the pawn on d6 is in the way of the rook on d5" in block
    assert moves_in_question_block("Что мне играть?", fen) == ""
    assert moves_in_question_block("Можно Nxa4?", fen) .endswith("NOT legal for the side to move; it is a move for Black")
    assert "- Rxd6: legal" in moves_in_question_block("Rxd6 — это мат?", fen)
    assert moves_in_question_block("e4", fen) == ""  # a bare square is not a move


@pytest.mark.unit
def test_kazakh_answers_carry_the_chess_terms():
    """The bishop came out as «пияз» (an onion) on the stand, 2026-10-04."""
    from src import prompt_builder
    from src.quick_reply import build_quick_messages, build_small_talk_messages

    assert "bishop — піл (слон), never «пияз»" in prompt_builder.KAZAKH_TERMS
    assert "піл" in prompt_builder.language_note("kk", "asked")
    assert prompt_builder.language_note("kk", "asked").endswith("]")
    assert "піл" in prompt_builder.language_note("kz", "interface")
    assert "піл" not in prompt_builder.language_note("ru", "message")
    assert "піл" in prompt_builder.language_note("kk", "unsupported:German")
    assert "піл" in prompt_builder.build_voice_prompt("SOUL", locale="kz")
    assert "піл" in prompt_builder.build_voice_prompt("SOUL", locale="en", language=("kk", "asked"))
    assert "піл" not in prompt_builder.build_voice_prompt("SOUL", locale="en")
    assert "піл" in build_quick_messages("x", "kk", None)[0]["content"]
    assert "піл" not in build_quick_messages("x", "ru", None)[0]["content"]
    assert "піл" in build_small_talk_messages("сәлем", "kz")[0]["content"]
