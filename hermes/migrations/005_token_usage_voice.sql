-- Migration 005: Add voice-only metering columns to token_usage
-- Voice (Gemini Live) rows carry no server-side token counts, so they record the
-- tool name (one row per voice tool call) and the session duration (one row per
-- session on disconnect) instead, so voice spend can be estimated from
-- tool-call counts + duration. Both nullable — text/analysis rows leave them
-- NULL. Additive only — never edit 001/004.

ALTER TABLE token_usage
    ADD COLUMN IF NOT EXISTS tool_name TEXT,
    ADD COLUMN IF NOT EXISTS duration_ms INTEGER;
