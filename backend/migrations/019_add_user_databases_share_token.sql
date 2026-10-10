-- Shared Databases, Step 0: per-database share tokens.
--
-- The owner mints an opaque token to share one database (collection); the token
-- resolves (read-only) to that database's meta and its games (scoped by
-- user_games.database_id). The owner revokes by setting share_token back to NULL.
-- The built-in default "My Games" database is NEVER shareable (enforced in the
-- API). Mirrors the per-game token added in migration 016.
--
-- Idempotent: re-running makes no further changes.
ALTER TABLE user_databases ADD COLUMN IF NOT EXISTS share_token TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS user_databases_share_token_idx
    ON user_databases (share_token) WHERE share_token IS NOT NULL;
