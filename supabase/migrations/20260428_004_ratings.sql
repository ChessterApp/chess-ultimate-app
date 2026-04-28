-- Migration: Rating System Tables
-- Phase 5: FIDE Elo Rating System
-- Tables: player_ratings, player_fide_ratings, rating_history

-- Player ratings (standard FIDE Elo)
CREATE TABLE player_ratings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL,
  organization_id UUID REFERENCES organizations(id),
  rating INT DEFAULT 1200,
  peak_rating INT DEFAULT 1200,
  k_factor INT DEFAULT 40,
  games_played INT DEFAULT 0,
  wins INT DEFAULT 0,
  draws INT DEFAULT 0,
  losses INT DEFAULT 0,
  league TEXT DEFAULT 'C'
    CHECK (league IN ('C', 'B', 'A', 'Master')),
  is_provisional BOOLEAN DEFAULT true,
  last_game_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, organization_id)
);

-- FIDE ID + official rating tracking (not calculated by Chesster)
CREATE TABLE player_fide_ratings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL UNIQUE,
  fide_id TEXT UNIQUE,
  standard_rating INT,
  rapid_rating INT,
  blitz_rating INT,
  title TEXT,
  federation TEXT DEFAULT 'KAZ',
  last_synced_at TIMESTAMPTZ,
  CONSTRAINT valid_fide_id CHECK (fide_id ~ '^\d{5,10}$')
);

-- Every rating change logged
CREATE TABLE rating_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL,
  source_type TEXT NOT NULL
    CHECK (source_type IN ('tournament', 'online_game')),
  source_id UUID,
  rating_before INT NOT NULL,
  rating_after INT NOT NULL,
  change INT NOT NULL,
  k_factor_used INT NOT NULL,
  calculated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_rating_history_user ON rating_history(user_id, calculated_at);
