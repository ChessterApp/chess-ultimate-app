-- Migration 007: Unified coach event log
-- One append-only row per instrumented moment in a coach turn (turn_start,
-- turn_end, tool_call, llm_error, stream_disconnect, ...) across the text and
-- voice surfaces. Correlates a message to its tool calls, cost, latency, and
-- errors via (session_id, turn_id) — the glue the fragmented telemetry tables
-- (coach_messages / token_usage / diagnostics.jsonl) never had.
-- Additive only — new table, touches nothing existing.

CREATE TABLE IF NOT EXISTS coach_events (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'info',   -- info | warn | error
  user_id TEXT,
  session_id TEXT,
  turn_id TEXT,
  surface TEXT NOT NULL,                   -- text | voice
  model TEXT,
  tool_name TEXT,
  duration_ms INTEGER,
  ok BOOLEAN,
  error_code TEXT,
  payload JSONB
);

-- All events for one session, in order (turn timeline reconstruction).
CREATE INDEX IF NOT EXISTS idx_coach_events_session
  ON coach_events (session_id);

-- Per-user activity, most-recent first.
CREATE INDEX IF NOT EXISTS idx_coach_events_user_created
  ON coach_events (user_id, created_at);

-- Event-type rollups over time (how many tool_calls / llm_errors per day).
CREATE INDEX IF NOT EXISTS idx_coach_events_type_created
  ON coach_events (event_type, created_at);

-- Error firehose: partial index keeps the error scan tiny vs the full table.
CREATE INDEX IF NOT EXISTS idx_coach_events_errors
  ON coach_events (created_at) WHERE severity = 'error';
