-- Migration 019: kb_topics + kb_positions — mirror of the coach's thematic knowledge base
-- The coach reads hermes/content/topics/*.yaml directly; these tables exist so the site
-- and the mobile app can show the same topics (a "Темы" section, links from lessons) and
-- so a methodologist can later edit in the database instead of YAML.
-- Filled by scripts/sync_kb_topics.py (idempotent upsert by slug). Idempotent.

CREATE TABLE IF NOT EXISTS kb_topics (
    slug TEXT PRIMARY KEY,
    phase TEXT NOT NULL CHECK (phase IN (
        'strategy', 'tactics', 'pawn_structure', 'typical_position',
        'opening', 'middlegame', 'endgame')),
    level INTEGER NOT NULL DEFAULT 2 CHECK (level BETWEEN 1 AND 4),
    title_ru TEXT NOT NULL,
    title_kk TEXT,
    title_en TEXT,
    summary_ru TEXT NOT NULL DEFAULT '',
    summary_kk TEXT,
    summary_en TEXT,
    key_ideas_ru JSONB NOT NULL DEFAULT '[]'::jsonb,
    typical_mistakes_ru JSONB NOT NULL DEFAULT '[]'::jsonb,
    lichess_themes TEXT[] NOT NULL DEFAULT '{}',
    eco_codes TEXT[] NOT NULL DEFAULT '{}',
    lesson_stems TEXT[] NOT NULL DEFAULT '{}',
    related TEXT[] NOT NULL DEFAULT '{}',
    model_games JSONB NOT NULL DEFAULT '[]'::jsonb,
    source TEXT,                                   -- yaml file the row came from
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kb_topics_phase_level ON kb_topics(phase, level);

CREATE TABLE IF NOT EXISTS kb_positions (
    id BIGSERIAL PRIMARY KEY,
    topic_slug TEXT NOT NULL REFERENCES kb_topics(slug) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    title_ru TEXT NOT NULL DEFAULT '',
    title_en TEXT,
    fen TEXT NOT NULL,
    side_to_move TEXT NOT NULL CHECK (side_to_move IN ('white', 'black')),
    moves TEXT,                                    -- numbered SAN from the start, if given
    plan_ru TEXT NOT NULL DEFAULT '',
    best_move TEXT,
    UNIQUE (topic_slug, ordinal)
);

-- Read-only for the anon/authenticated roles (RLS on, select allowed).
ALTER TABLE kb_topics ENABLE ROW LEVEL SECURITY;
ALTER TABLE kb_positions ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'kb_topics' AND policyname = 'kb_topics_read') THEN
        CREATE POLICY kb_topics_read ON kb_topics FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'kb_positions' AND policyname = 'kb_positions_read') THEN
        CREATE POLICY kb_positions_read ON kb_positions FOR SELECT USING (true);
    END IF;
END $$;
