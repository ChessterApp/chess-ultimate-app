-- Phase 1 (Collection Share): one revocable, opaque token per user that shares
-- their ENTIRE "My Games" collection. Mirrors the per-game share_token added in
-- migration 016, but at the collection level: one row per owner.
--
-- Revoke semantics match per-game share exactly — revoking removes the token so
-- no lookup can resolve it (here the whole row is deleted). Re-sharing mints a
-- fresh token. user_id is UNIQUE so minting is idempotent.
CREATE TABLE IF NOT EXISTS user_game_collection_shares (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT UNIQUE NOT NULL,
    token TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS user_game_collection_shares_token_idx
    ON user_game_collection_shares (token);

ALTER TABLE user_game_collection_shares ENABLE ROW LEVEL SECURITY;
