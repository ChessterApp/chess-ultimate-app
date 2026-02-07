-- Migration 005: Debut (Opening Repertoire) Tables
-- Status: Tables already exist in Supabase with data (5 repertoires, 19 nodes)
-- This file serves as documentation / disaster recovery SQL.

-- opening_repertoires
CREATE TABLE IF NOT EXISTS opening_repertoires (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    color TEXT NOT NULL CHECK (color IN ('w', 'b')),
    description TEXT,
    is_primary BOOLEAN DEFAULT false,
    starting_fen TEXT,
    starting_move_line TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_repertoires_user_id ON opening_repertoires(user_id);

-- opening_nodes
CREATE TABLE IF NOT EXISTS opening_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repertoire_id UUID NOT NULL REFERENCES opening_repertoires(id) ON DELETE CASCADE,
    parent_id UUID REFERENCES opening_nodes(id) ON DELETE CASCADE,
    fen TEXT NOT NULL,
    move_san TEXT,
    move_uci TEXT,
    move_number INTEGER DEFAULT 0,
    is_white_move BOOLEAN,
    opening_name TEXT,
    eco_code TEXT,
    notes TEXT,
    priority INTEGER DEFAULT 0,
    is_critical BOOLEAN DEFAULT false,
    times_trained INTEGER DEFAULT 0,
    times_correct INTEGER DEFAULT 0,
    last_trained_at TIMESTAMPTZ,
    next_review_at TIMESTAMPTZ,
    ease_factor FLOAT DEFAULT 2.5,
    interval_days INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_nodes_repertoire ON opening_nodes(repertoire_id);
CREATE INDEX IF NOT EXISTS idx_nodes_parent ON opening_nodes(parent_id);
CREATE INDEX IF NOT EXISTS idx_nodes_fen ON opening_nodes(fen);

-- opening_game_links
CREATE TABLE IF NOT EXISTS opening_game_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL REFERENCES opening_nodes(id) ON DELETE CASCADE,
    game_source TEXT NOT NULL,
    game_id TEXT,
    game_pgn TEXT,
    white_player TEXT,
    black_player TEXT,
    white_elo INTEGER,
    black_elo INTEGER,
    result TEXT,
    date_played TEXT,
    event_name TEXT,
    move_reached TEXT,
    user_outcome TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_game_links_node ON opening_game_links(node_id);

-- opening_arrows
CREATE TABLE IF NOT EXISTS opening_arrows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL REFERENCES opening_nodes(id) ON DELETE CASCADE,
    from_square TEXT NOT NULL,
    to_square TEXT NOT NULL,
    color TEXT DEFAULT 'green',
    opacity FLOAT DEFAULT 0.8,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_arrows_node ON opening_arrows(node_id);

-- RLS Policies
ALTER TABLE opening_repertoires ENABLE ROW LEVEL SECURITY;
ALTER TABLE opening_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE opening_game_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE opening_arrows ENABLE ROW LEVEL SECURITY;
