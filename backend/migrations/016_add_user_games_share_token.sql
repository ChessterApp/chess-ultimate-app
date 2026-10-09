-- Phase 3a: revocable share tokens for a user's own saved games.
-- The owner generates an opaque token to share a game; recipients must be
-- signed in to view the game itself, and the owner can revoke the link by
-- setting share_token back to NULL.
ALTER TABLE user_games ADD COLUMN IF NOT EXISTS share_token text;
CREATE UNIQUE INDEX IF NOT EXISTS user_games_share_token_idx ON user_games (share_token) WHERE share_token IS NOT NULL;
