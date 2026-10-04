-- Migration 015: Create user_onboarding table
-- Created: 2026-10-04
-- Description: Persists the consumer onboarding funnel answers tied to the Clerk
--              user (created at the END of onboarding) plus the server-derived
--              skill_tier + starting_level. Upsert keyed on clerk_user_id, same
--              pattern as pending_onboarding.
--
-- NOTE: Do NOT apply from Ralph. Applied later via the normal migration path.

BEGIN;

CREATE TABLE IF NOT EXISTS user_onboarding (
    clerk_user_id TEXT PRIMARY KEY,

    -- Raw funnel answers
    attribution TEXT,
    experience TEXT,
    platform TEXT,
    platform_username TEXT,
    online_rating INTEGER,
    elo_rating INTEGER,
    no_rating BOOLEAN,
    focus_areas JSONB,        -- array of strings
    challenge TEXT,
    practice_time TEXT,
    goal TEXT,
    timeline TEXT,

    -- Server-derived (see services/onboarding_tier.py)
    skill_tier TEXT,
    starting_level INTEGER,
    onboarding_complete BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Shared updated_at trigger helper (idempotent — other tables rely on it too).
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_user_onboarding_updated_at ON user_onboarding;
CREATE TRIGGER update_user_onboarding_updated_at
    BEFORE UPDATE ON user_onboarding
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE user_onboarding ENABLE ROW LEVEL SECURITY;

COMMIT;
