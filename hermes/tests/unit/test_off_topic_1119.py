"""Tester, 19.11: «напиши мне сочинение про лето» got three paragraphs, «25 * 4» was worked out, a recipe of draniki
was read out in voice — and the reaction before each said «Посмотрю, что можно сказать о рецепте драников». The coach
helps only with chess (CHESS_ONLY_LAYER, text and voice), and the reaction for such a message is the mark the server
never shows (quick_reply.OFF_TOPIC_MARK, withhold_off_topic)."""

import pytest

from src import prompt_builder
from src.quick_reply import (OFF_TOPIC_MARK, build_quick_messages, is_off_topic_reaction,
                             withhold_off_topic)


def _run(chunks):
    out = []
    feed = withhold_off_topic(out.append)
    for c in chunks:
        feed(c)
    return "".join(out)


@pytest.mark.unit
class TestTheReaction:
    def test_the_mark_never_reaches_the_student(self):
        assert _run(["OFF", "TOP", "IC"]) == ""
        assert _run([" OFFTOPIC.", " more"]) == ""
        assert _run(["offtopic"]) == ""

    def test_a_real_reaction_goes_out_whole_and_in_order(self):
        assert _run(["Посмотрю", " на позицию."]) == "Посмотрю на позицию."
        assert _run(["O", "k, смотрю ", "дебют."]) == "Ok, смотрю дебют."
        assert _run(["OF", "TEN"]) == "OFTEN"  # starts like the mark, is not it

    def test_the_prompt_asks_for_the_mark_for_a_message_not_about_chess(self):
        system = build_quick_messages("напиши мне сочинение про лето", "ru", None)[0]["content"]
        assert OFF_TOPIC_MARK in system and "{mark}" not in system
        assert "homework" in system and "recipe" in system

    def test_the_mark_is_told_apart(self):
        assert is_off_topic_reaction("OFFTOPIC") and is_off_topic_reaction(" offtopic.")
        assert not is_off_topic_reaction("Посмотрю на позицию.") and not is_off_topic_reaction(None)


@pytest.mark.unit
class TestTheAnswer:
    def test_the_text_coach_helps_only_with_chess(self):
        prompt = prompt_builder.build_system_prompt("SOUL", locale="ru")
        assert prompt_builder.CHESS_ONLY_LAYER in prompt
        layer = prompt_builder.CHESS_ONLY_LAYER
        assert "do NOT do it" in layer and "children" in layer and "Only ask: do not start it" in layer

    def test_the_voice_coach_too(self):
        assert prompt_builder.CHESS_ONLY_LAYER in prompt_builder.build_voice_prompt("SOUL", locale="ru")

    def test_the_rule_sits_in_the_cached_part(self):
        static, _ = prompt_builder.build_system_prompt("SOUL", locale="ru", board_fen="8/8/8/8/8/8/8/K6k w - - 0 1",
                                                      return_parts=True)
        assert prompt_builder.CHESS_ONLY_LAYER in static
        assert prompt_builder.PROMPT_TEMPLATE_VERSION == "23"
