"""20.11: a voice answer came ~10 s after the student stopped on production; 3-4 s of it went to looking a lesson up
before a general question, and the quick reaction nobody hears held the answer's first words back. A spoken turn
(speech=true) is answered at once: the lesson lookup tools are left out unless the student asks for a lesson, a
course, an example or the board (tool_selector.spoken_lookup_skipped)."""

import pytest

from src import server
from src.tool_selector import SPOKEN_LOOKUP_TOOLS, spoken_lookup_skipped


@pytest.mark.unit
class TestWhichTurns:
    @pytest.mark.parametrize("q", [
        "Как отвечать на e4?", "Как перестать зевать фигуры?", "Когда нельзя делать рокировку?",
        "Объясни простыми словами, что такое связка.", "Бұл позицияда ең жақсы жүріс қандай?",
        "Привет, ты меня слышишь?", "What is a fork?", "Какой здесь лучший ход?",
    ])
    def test_a_plain_question_is_answered_at_once(self, q):
        assert spoken_lookup_skipped(q)

    @pytest.mark.parametrize("q", [
        "Какой урок мне пройти дальше?", "Продолжим курс", "Что дальше по программе?",
        "Покажи пример связки", "Поставь на доску защиту Каро-Канн", "Келесі сабақ қандай?",
        "Мысал көрсет", "Show me an example of a pin", "Which lesson is next?",
        "Дай мне задачу на вилку.", "Давай сыграем, я белыми.", "Разминка: дай мне 5 задач", "Let's play a game",
        "Партия ойнайық",
    ])
    def test_a_lesson_an_example_or_the_board_keeps_the_lookup(self, q):
        assert not spoken_lookup_skipped(q)


class _Agent:
    def __init__(self, **kwargs):
        self.tools = [{"type": "function", "function": {"name": n, "description": ""}}
                      for n in ("board_control", "analyze_position", "get_topic", "get_learning_path", "get_lesson",
                                "get_puzzle")]
        self.valid_tool_names = {t["function"]["name"] for t in self.tools}


@pytest.mark.unit
class TestTheAgent:
    def _agent(self, monkeypatch, spoken_quick):
        import run_agent
        monkeypatch.setattr(run_agent, "AIAgent", _Agent)
        monkeypatch.setattr(server, "_arm_gemini_reasoning", lambda a: None)
        monkeypatch.setattr(server, "_watch_stream_cuts", lambda a: None)
        monkeypatch.setattr(server.config, "COACH_TOOL_SUBSET", False)
        import src.llm_transport as lt
        monkeypatch.setattr(lt, "install", lambda a: None)
        return server._create_agent(model="openai/gpt-6.1-terra", system_prompt="", user_query="Как отвечать на e4?",
                                    spoken_quick=spoken_quick)

    def test_a_spoken_quick_turn_has_no_lookup_tools(self, monkeypatch):
        agent = self._agent(monkeypatch, True)
        names = {t["function"]["name"] for t in agent.tools}
        assert not names & SPOKEN_LOOKUP_TOOLS and {"get_puzzle", "analyze_position"} <= names
        assert agent.valid_tool_names == names

    def test_a_typed_turn_keeps_them(self, monkeypatch):
        agent = self._agent(monkeypatch, False)
        assert SPOKEN_LOOKUP_TOOLS <= {t["function"]["name"] for t in agent.tools}
