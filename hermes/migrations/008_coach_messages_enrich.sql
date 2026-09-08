-- Migration 008: Enrich coach_messages with per-turn telemetry
-- Stamps each message row with the turn correlation id, the model + prompt
-- version that produced it, and (on assistant rows) latency and token counts so
-- a conversation can be joined to coach_events and token_usage without guessing.
-- ALL columns additive/nullable — never edit 001, byte-safe on existing rows.

ALTER TABLE coach_messages
    ADD COLUMN IF NOT EXISTS turn_id TEXT,
    ADD COLUMN IF NOT EXISTS model TEXT,
    ADD COLUMN IF NOT EXISTS prompt_version TEXT,
    ADD COLUMN IF NOT EXISTS latency_ms INTEGER,
    ADD COLUMN IF NOT EXISTS client_ts TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS prompt_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS completion_tokens INTEGER;

-- Join a turn's user + assistant rows (and its coach_events) by turn_id.
CREATE INDEX IF NOT EXISTS idx_coach_messages_turn ON coach_messages (turn_id);
