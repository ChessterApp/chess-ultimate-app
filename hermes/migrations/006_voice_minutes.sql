-- Migration 006: Voice Mode minutes ledger
-- Voice Mode is metered by minutes per calendar month (UTC). Each live session
-- accumulates its spoken seconds into one row here via heartbeats; the monthly
-- quota is the SUM of `seconds` for a user within a `month_key` (e.g. 2026-09).
-- Additive only — new table, touches nothing existing.

CREATE TABLE IF NOT EXISTS voice_usage (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           TEXT NOT NULL,
    session_id        TEXT NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    seconds           INTEGER NOT NULL DEFAULT 0,
    month_key         TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- One row per (user, session): heartbeats accumulate into it.
    UNIQUE (user_id, session_id)
);

-- Monthly-usage lookups sum `seconds` for a (user_id, month_key) pair.
CREATE INDEX IF NOT EXISTS idx_voice_usage_user_month
    ON voice_usage (user_id, month_key);
