-- Tournament Calendar Schema
-- Phase 4: Tournament CRUD, calendar UI, registration, results

CREATE TABLE tournaments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT,
  location TEXT NOT NULL,
  location_coordinates POINT,
  city TEXT,
  country TEXT DEFAULT 'KZ',
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  registration_deadline TIMESTAMPTZ NOT NULL,
  time_control TEXT NOT NULL,
  format TEXT
    CHECK (format IN ('swiss', 'round_robin', 'knockout', 'other')),
  max_participants INT,
  entry_fee DECIMAL(10,2) DEFAULT 0,
  currency TEXT DEFAULT 'KZT',
  prize_fund DECIMAL(10,2),
  prize_distribution JSONB,
  age_categories TEXT[],
  rating_category TEXT,
  min_rating INT,
  max_rating INT,
  is_fide_rated BOOLEAN DEFAULT false,
  organizer_org_id UUID REFERENCES organizations(id),
  created_by TEXT NOT NULL,
  status TEXT DEFAULT 'upcoming'
    CHECK (status IN ('upcoming', 'registration_open', 'registration_closed',
                      'in_progress', 'completed', 'cancelled')),
  rules_url TEXT,
  image_url TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_tournaments_status ON tournaments(status);
CREATE INDEX idx_tournaments_dates ON tournaments(start_date, end_date);
CREATE INDEX idx_tournaments_org ON tournaments(organizer_org_id);

CREATE TABLE tournament_registrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tournament_id UUID NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  player_name TEXT NOT NULL,
  rating_at_registration INT,
  age_category TEXT,
  payment_status TEXT DEFAULT 'pending'
    CHECK (payment_status IN ('pending', 'paid', 'refunded', 'waived')),
  payment_intent_id TEXT,
  registration_status TEXT DEFAULT 'pending'
    CHECK (registration_status IN ('pending', 'confirmed', 'waitlisted', 'cancelled')),
  registered_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(tournament_id, user_id)
);

CREATE INDEX idx_tournament_reg_tournament ON tournament_registrations(tournament_id);
CREATE INDEX idx_tournament_reg_user ON tournament_registrations(user_id);

CREATE TABLE tournament_games (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tournament_id UUID NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
  round INT NOT NULL,
  board INT,
  white_player_id TEXT NOT NULL,
  black_player_id TEXT NOT NULL,
  result TEXT NOT NULL
    CHECK (result IN ('1-0', '0-1', '1/2-1/2', '*', '+/-', '-/+')),
  white_rating_before FLOAT,
  black_rating_before FLOAT,
  pgn TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(tournament_id, round, board)
);

CREATE INDEX idx_tournament_games_tournament ON tournament_games(tournament_id);
CREATE INDEX idx_tournament_games_round ON tournament_games(tournament_id, round);

CREATE TABLE tournament_standings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tournament_id UUID NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  rank INT,
  score FLOAT DEFAULT 0,
  buchholz FLOAT DEFAULT 0,
  sonneborn_berger FLOAT DEFAULT 0,
  wins INT DEFAULT 0,
  draws INT DEFAULT 0,
  losses INT DEFAULT 0,
  rating_change FLOAT,
  performance_rating FLOAT,
  UNIQUE(tournament_id, user_id)
);

CREATE INDEX idx_tournament_standings_tournament ON tournament_standings(tournament_id);
CREATE INDEX idx_tournament_standings_rank ON tournament_standings(tournament_id, rank);
