-- Migration 012: Create user_chess_profiles table
-- Stores linked chess platform accounts and ratings for coaching features

CREATE TABLE IF NOT EXISTS user_chess_profiles (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT UNIQUE NOT NULL,
    lichess_username TEXT,
    chesscom_username TEXT,
    lichess_rating INTEGER,
    chesscom_rating INTEGER,
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_chess_profiles_user_id ON user_chess_profiles(user_id);

-- Auto-update updated_at on row changes
CREATE TRIGGER update_user_chess_profiles_updated_at
    BEFORE UPDATE ON user_chess_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE user_chess_profiles ENABLE ROW LEVEL SECURITY;
