-- 011_user_profiles.sql
-- The per-student profile table read by prompt_builder (user_profile.py) and
-- written by the Phase 1 memory writer (memory_writer.py). The code has
-- referenced this table since the beginning, but no migration ever created it —
-- reads 404'd fail-open to a default profile and writer upserts silently
-- no-oped. Idempotent; service-key access only (RLS enabled, no policies).

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    rating INTEGER NOT NULL DEFAULT 1200,
    goals JSONB NOT NULL DEFAULT '[]'::jsonb,
    preferred_openings JSONB NOT NULL DEFAULT '[]'::jsonb,
    weaknesses JSONB NOT NULL DEFAULT '[]'::jsonb,
    style TEXT NOT NULL DEFAULT 'unknown',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION set_user_profiles_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_user_profiles_updated_at ON user_profiles;
CREATE TRIGGER trg_user_profiles_updated_at
    BEFORE UPDATE ON user_profiles
    FOR EACH ROW
    EXECUTE FUNCTION set_user_profiles_updated_at();

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
