# PLAN: Fix Lichess Game Loading on Board

## Problem

When user asks "Find the last game by CheckmateComedian on Lichess and load it on the board", the coach:
1. Calls `lichess_game_import` — which fetches PGN from Lichess API (works fine)
2. Gets back only a **summary** (import count, results breakdown) — **PGN text is discarded**
3. Can't call `board_control(load_pgn)` because it never received the PGN
4. Gives up and says "I couldn't load the game"

## Root Cause

`lichess_game_import` in `external_apis.py` fetches full PGN from Lichess but only returns:
```json
{"imported": 50, "source": "lichess", "username": "...", "results": {"1-0": 20, ...}, "summary": "Imported 50 games..."}
```

The actual PGN text is thrown away. The model has no way to chain import → load_pgn.

## Fix — 2 changes

### 1. `external_apis.py` — Return last N games' PGN in the tool result

Modify `lichess_game_import()` to include the **last game's PGN** (or last N) in the result dict:
```python
return {
    "imported": len(games),
    "source": "lichess",
    "username": username,
    "results": results_summary,
    "summary": f"Imported {len(games)} games from Lichess for {username}.",
    "last_games": [
        {"pgn": g["pgn"], "white": g["white"], "black": g["black"], "result": g["result"], "date": g["date"]}
        for g in games[:3]  # Return the 3 most recent games with full PGN
    ],
}
```

This gives the model the PGN text to use with `board_control(load_pgn)`.

### 2. `prompt_builder.py` — Add workflow instruction

Add to the tool instructions:
```
### Lichess/Chess.com Game Loading Workflow
When the user asks to load a game from Lichess or Chess.com:
1. Call lichess_game_import (or chesscom_game_import) with the username and max_games=1
2. The result includes last_games[].pgn — take the PGN from there
3. Call board_control with action_type="load_pgn" and pgn=<the PGN from step 2>
Never say you can't load the game — always follow this 2-step workflow.
```

## Not in scope

- New dedicated "fetch single game" tool — overkill, the import tool already fetches PGN
- Storing PGN in Supabase for later retrieval — the tool already handles this

## Files to change

1. `/root/chess-app/hermes/src/tools/external_apis.py` — return `last_games` with PGN
2. `/root/chess-app/hermes/src/prompt_builder.py` — add game loading workflow instruction

## Testing

1. `curl -X POST localhost:8642/api/coach/chat` with message "Find last game by CheckmateComedian on Lichess and load it on the board"
2. Verify response includes `board_actions` with `load_pgn` action containing PGN
3. Verify the board_action PGN is valid and matches the latest Lichess game
