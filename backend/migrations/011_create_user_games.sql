-- Migration 011: Create user_games table
-- Stores user-saved chess games for the "My Games" feature

CREATE TABLE IF NOT EXISTS user_games (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT,
    white TEXT,
    black TEXT,
    white_elo INTEGER,
    black_elo INTEGER,
    result TEXT,
    date TEXT,
    event TEXT,
    eco TEXT,
    opening_name TEXT,
    pgn TEXT NOT NULL,
    notes TEXT,
    tags TEXT[] DEFAULT '{}',
    is_favorite BOOLEAN DEFAULT FALSE,
    source TEXT DEFAULT 'manual',
    deleted_at TIMESTAMPTZ DEFAULT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_games_user_id ON user_games(user_id);

CREATE INDEX IF NOT EXISTS idx_user_games_deleted ON user_games(deleted_at) WHERE deleted_at IS NULL;

ALTER TABLE user_games ENABLE ROW LEVEL SECURITY;
