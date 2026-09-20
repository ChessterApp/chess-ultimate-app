-- Migration 018: coach_boards + session title / active board
-- A session used to persist one FEN (board_state) that was never read back.
-- Boards are now first-class: the study board, puzzles, master games opened
-- from search and (later) a game against the coach, each with its own PGN,
-- ply, orientation and annotations, one of them active. Idempotent.

ALTER TABLE coach_sessions ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT '';
ALTER TABLE coach_sessions ADD COLUMN IF NOT EXISTS active_board_id UUID;

CREATE TABLE IF NOT EXISTS coach_boards (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES coach_sessions(id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'study'
        CHECK (kind IN ('study', 'puzzle', 'game', 'master_game')),
    title TEXT NOT NULL DEFAULT '',
    pgn TEXT NOT NULL DEFAULT '',
    fen TEXT NOT NULL,
    ply INTEGER NOT NULL DEFAULT 0,
    orientation TEXT NOT NULL DEFAULT 'white' CHECK (orientation IN ('white', 'black')),
    annotations JSONB NOT NULL DEFAULT '{}'::jsonb,
    puzzle JSONB,
    game_state JSONB,
    source JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coach_boards_session_id ON coach_boards(session_id);
