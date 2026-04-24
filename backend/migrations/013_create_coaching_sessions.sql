-- Migration 013: Create coaching_sessions table
-- Stores Hermes coaching chat sessions with board state

CREATE TABLE IF NOT EXISTS coaching_sessions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT,
    messages JSONB DEFAULT '[]'::JSONB,
    board_state JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coaching_sessions_user_id ON coaching_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_coaching_sessions_updated ON coaching_sessions(updated_at DESC);

-- Auto-update updated_at on row changes
CREATE TRIGGER update_coaching_sessions_updated_at
    BEFORE UPDATE ON coaching_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE coaching_sessions ENABLE ROW LEVEL SECURITY;
