-- Migration 018: user_databases + database_id on user_games
--
-- Database Management, Phase 1. Lets a user own multiple named game "databases"
-- (collections). Mirrors the user_games conventions: user_id is TEXT (Clerk id),
-- soft-delete via deleted_at, RLS enabled. The static "Master Database" pill is a
-- built-in frontend concept (TWIC) and is NEVER stored here.
--
-- Fully idempotent: re-running makes no further changes (IF NOT EXISTS guards +
-- NOT EXISTS / IS NULL backfill predicates).
CREATE TABLE IF NOT EXISTS user_databases (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_user_databases_user_id ON user_databases(user_id);
-- case-insensitive unique name per user among LIVE (non-deleted) rows
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_databases_user_name_live
  ON user_databases(user_id, lower(name)) WHERE deleted_at IS NULL;
-- only one default per user among live rows
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_databases_one_default
  ON user_databases(user_id) WHERE is_default = TRUE AND deleted_at IS NULL;
ALTER TABLE user_databases ENABLE ROW LEVEL SECURITY;

ALTER TABLE user_games ADD COLUMN IF NOT EXISTS database_id UUID REFERENCES user_databases(id);
CREATE INDEX IF NOT EXISTS idx_user_games_database_id ON user_games(database_id);

-- BACKFILL (idempotent): one default "My Games" db per existing user, then stamp games.
INSERT INTO user_databases (user_id, name, is_default)
SELECT DISTINCT user_id, 'My Games', TRUE
FROM user_games ug
WHERE ug.user_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM user_databases d
    WHERE d.user_id = ug.user_id AND d.is_default = TRUE AND d.deleted_at IS NULL
  );

UPDATE user_games ug
SET database_id = d.id
FROM user_databases d
WHERE d.user_id = ug.user_id AND d.is_default = TRUE AND d.deleted_at IS NULL
  AND ug.database_id IS NULL;
