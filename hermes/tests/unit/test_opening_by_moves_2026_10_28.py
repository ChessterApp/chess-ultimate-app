"""Stand run 28.10, voice: «Как называется дебют, где белые играют е4, а чёрные отвечают е6?» — lookup_opening
answered {"found": false} (it looked for a NAME in the words) and the coach said it could not tell the French
Defence. Now the moves listed in a question that asks for the name are named by the ECO book."""

import json

import pytest
from tools.registry import registry

import src.tools.opening_lookup  # noqa: F401 — registers lookup_opening
from src.opening_knowledge import line_named, plan_opening


@pytest.mark.unit
@pytest.mark.parametrize("text, moves, name", [
    ("Как называется дебют, где белые играют е4, а чёрные отвечают е6?", ["e4", "e6"], "French Defense"),
    ("Что за дебют 1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6?",
     ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6"], "Sicilian Defense: Najdorf Variation"),
    ("Как называется дебют: е4 е5, конь f3 конь c6, слон b5?", ["e4", "e5", "Nf3", "Nc6", "Bb5"], "Ruy Lopez"),
    ("What opening is 1.d4 Nf6 2.c4 e6 3.Nc3 Bb4?", ["d4", "Nf6", "c4", "e6", "Nc3", "Bb4"], "Nimzo-Indian Defense"),
    ("Бұл қандай дебют: d4 d5 c4?", ["d4", "d5", "c4"], "Queen's Gambit"),
    ("Как называется дебют e2-e4 e7-e5 g1-f3?", ["e4", "e5", "Nf3"], "King's Knight Opening"),
    ("Какой это дебют: 1.e4 e5 2.f4", ["e4", "e5", "f4"], "King's Gambit"),
])
def test_the_moves_of_a_name_question_are_named_by_the_book(text, moves, name):
    assert line_named(text) == moves
    plan = plan_opening(text)
    assert plan is not None and plan.name == name
    assert plan.block.startswith("The moves the student named")


@pytest.mark.unit
@pytest.mark.parametrize("text", [
    "Что будет, если я сыграю е4?",      # a move, not a name asked for
    "Как называется ход е4?",            # one move is no opening
    "Почему после е4 е5 нельзя брать?",  # moves, but no name asked for
])
def test_no_opening_without_a_name_asked_for_two_plies(text):
    assert plan_opening(text) is None


@pytest.mark.unit
def test_a_named_opening_is_found_as_before():
    plan = plan_opening("Как называется сицилианская защита?")
    assert plan is not None and plan.name == "Sicilian Defense"
    assert not plan.block.startswith("The moves the student named")


@pytest.mark.unit
def test_the_voice_tool_names_the_moves_the_model_wrote_out():
    out = json.loads(registry.dispatch("lookup_opening", {
        "pgn": "1.e4 e6", "question": "Как называется дебют, где белые играют е4, а чёрные отвечаю"}))
    assert out["found"] and out["name"] == "French Defense"
