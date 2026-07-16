# Plan: Coach Conversation Memory

## Problem

The AI coach has **zero working memory**. Each message is treated as a brand new conversation:
- `session.messages` are stored in-memory but **never passed to the LLM**
- The frontend sends only `{message, fen, session_id}` — no history array
- `_create_agent()` uses `skip_memory=True` and `persist_session=False`
- Sessions are in-memory only — lost on Hermes restart

Result: user says "Find games by CheckmateComedian on Lichess", coach imports 50 games. Next message "Load his last game" — coach asks "who?" because it has no memory of the previous turn.

## Root Cause (server.py:379)

```python
response_text = await loop.run_in_executor(None, agent.chat, body.message)
```

Only `body.message` (current turn) is passed. `session.messages` (stored history) is never injected.

## Fix — 2 files, minimal changes

### File 1: `hermes/src/server.py` — Inject conversation history into the LLM call

**Change in `coach_chat()` (line ~364-379):**

Before creating the agent, build a context string from `session.messages` and prepend it to the user's message (or inject into system prompt).

**Approach A (prepend to user message)** — simpler, works with any model:
```python
# Build conversation context from session history
history_messages = session.messages[:-1]  # exclude the just-added user message
if history_messages:
    # Keep last N messages to stay within context window
    recent = history_messages[-20:]  # last 10 turns (20 messages)
    history_text = "\n".join(f"[{m.role}]: {m.content}" for m in recent)
    augmented_message = f"Previous conversation:\n{history_text}\n\nCurrent message:\n{body.message}"
else:
    augmented_message = body.message

# Route model based on original message (not augmented)
model = _resolve_model(None, body.message)
# ...
response_text = await loop.run_in_executor(None, agent.chat, augmented_message)
```

This mirrors what the `/v1/chat/completions` endpoint already does (lines 264-269) — proven pattern.

**Approach B (inject into system prompt)** — cleaner separation:
```python
if history_messages:
    recent = history_messages[-20:]
    history_block = "\n".join(f"{m.role}: {m.content}" for m in recent)
    system_prompt += f"\n\n## Conversation So Far\n{history_block}"
```

**Recommendation: Approach A** — it's already used in the OpenAI-compatible endpoint, less risk of bloating the system prompt, and the model sees conversation context as a natural continuation.

### File 2: `frontend/src/components/coach/CoachChat.tsx` — No change needed

The frontend already sends `session_id` and the backend already tracks messages per session. The fix is entirely server-side.

### Optional: Persist sessions to SQLite (cross-restart memory)

Currently sessions are in-memory (`dict`). On Hermes restart, all history is lost. To fix:

**Add to `sessions.py`:**
- SQLite backing store (the PRD mentions FTS5 but we can start simpler)
- Save messages on `add_message()`
- Load on `get()`

This is a **nice-to-have** for this PR — the critical fix is injecting history into the LLM call. Persistence can be Phase 2.

### Cross-session memory (PRD Phase 2)

The PRD envisions searchable memory across sessions (FTS5). Not in scope for this fix — the immediate problem is that the coach can't remember what was said 1 message ago.

## Testing

1. Send "Find games by CheckmateComedian on Lichess" → coach should import games
2. Send "Load his last game" → coach should know who "his" refers to (CheckmateComedian)
3. Send "What opening did he play?" → coach should still have context
4. Restart Hermes → same session should lose history (expected until persistence is added)

## Files Changed

| File | Change |
|------|--------|
| `hermes/src/server.py` | Inject session history into `agent.chat()` call |

## Risk

- **Token usage**: History adds tokens. Capped at 20 messages (~10 turns) to limit cost.
- **No breakage**: The change only affects `/api/coach/chat` — the OpenAI-compatible endpoint is untouched.
- **Model routing**: Uses `body.message` (not augmented) for routing, so keywords still work correctly.
