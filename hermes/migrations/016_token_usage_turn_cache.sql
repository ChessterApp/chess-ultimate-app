-- Migration 016: token_usage.turn_id + cached_tokens
-- turn_id joins a usage row to coach_messages / coach_events of the same turn
-- (the dashboard could not tell which answer a cost belonged to).
-- cached_tokens is the part of prompt_tokens served from the provider's prompt
-- cache, so caching can be verified from data. Idempotent.

ALTER TABLE token_usage ADD COLUMN IF NOT EXISTS turn_id TEXT;
ALTER TABLE token_usage ADD COLUMN IF NOT EXISTS cached_tokens INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_token_usage_turn_id ON token_usage(turn_id);
