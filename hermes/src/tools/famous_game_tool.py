"""Tool: famous_game — a famous game named in the student's words, with its verified score.

The text coach puts it on the board before it answers (server pre-step, 2026-10-08); the voice
coach had nothing of the kind and searched for the game or told it from memory, the way the text
coach got the Opera game wrong before the pre-step. The browser calls this tool on the student's
words (useGeminiLive), and the voice model may call it too (2026-10-12).
"""

import json

from tools.registry import registry

FAMOUS_GAME_SCHEMA = {
    "name": "famous_game",
    "description": (
        "A famous game the student names («оперная партия Морфи», «бессмертная партия», \"the Immortal "
        "Game\"): puts its verified score on the board and returns the moves and facts to tell it from. "
        "Use it instead of searching for such a game or telling it from memory."
    ),
    "parameters": {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "The student's words naming the game."}},
        "required": ["text"],
    },
}


def _handle_famous_game(args: dict, **kwargs) -> str:
    from src.famous_games import famous_game

    found = famous_game(str(args.get("text") or ""))
    if not found:
        return json.dumps({"found": False})
    return json.dumps({
        "found": True,
        "name": found["name"],
        "facts": found["block"],
        "board_actions": [{"type": "load_pgn", "pgn": found["pgn"]}],
    }, ensure_ascii=False)


registry.register(
    name="famous_game",
    toolset="chess",
    schema=FAMOUS_GAME_SCHEMA,
    handler=_handle_famous_game,
    description="A famous game by name, with its verified score, on the board.",
    emoji="🏛️",
)
