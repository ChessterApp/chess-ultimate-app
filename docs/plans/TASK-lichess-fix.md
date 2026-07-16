# Task: Fix Lichess and Chess.com game import to return PGN

## Problem
`lichess_game_import` and `chesscom_game_import` in `hermes/src/tools/external_apis.py` fetch PGN from APIs but discard it — only return summary counts. The model cannot chain import -> board_control(load_pgn) because it never gets the PGN text.

## Changes needed

### 1. hermes/src/tools/external_apis.py

In `lichess_game_import()`, add `last_games` field to the return dict with the 3 most recent games including full PGN:

```python
return {
    "imported": len(games),
    "source": "lichess",
    "username": username,
    "results": results_summary,
    "summary": f"Imported {len(games)} games from Lichess for {username}.",
    "last_games": [
        {"pgn": g["pgn"], "white": g["white"], "black": g["black"], "result": g["result"], "date": g["date"]}
        for g in games[:3]
    ],
}
```

Do the same for `chesscom_game_import()` — add `last_games` with last 3 games including PGN.

### 2. hermes/src/prompt_builder.py

Add a workflow instruction section after the board_control section in the tool instructions text. Add this block:

```
### Lichess/Chess.com Game Loading Workflow
When the user asks to find, load, or show a game from Lichess or Chess.com:
1. Call lichess_game_import or chesscom_game_import with the username and max_games=1
2. The result includes last_games with pgn field — take the PGN from there
3. Call board_control with action_type="load_pgn" and pgn=the PGN from step 2
Never say you cannot load the game — always follow this 2-step workflow.
```

### 3. Deploy

After making changes:
- `export HOME=/root`
- `git add hermes/src/tools/external_apis.py hermes/src/prompt_builder.py`
- `git commit -m "fix: return PGN in game import results for board loading"`
- `git push`
- `cp hermes/src/tools/external_apis.py /root/hermes-chess/src/tools/external_apis.py`
- `cp hermes/src/prompt_builder.py /root/hermes-chess/src/prompt_builder.py`
- `pm2 restart hermes-chess`

### 4. Test

Test the actual endpoint with curl:
- Lichess test: `curl -X POST http://localhost:8642/api/coach/chat -H "Content-Type: application/json" -d '{"message": "Find the last game by CheckmateComedian on Lichess and load it on the board", "session_id": "test-lichess-fix"}'`
- Verify response includes board_actions with load_pgn action
- Chess.com test: `curl -X POST http://localhost:8642/api/coach/chat -H "Content-Type: application/json" -d '{"message": "Find hikaru last game on chess.com and load it", "session_id": "test-chesscom-fix"}'`
- Verify board_actions present in response

## Important
- Do NOT modify any other files
- Do NOT change the tool schema — only the return values
- `export HOME=/root` before git/pm2 commands
