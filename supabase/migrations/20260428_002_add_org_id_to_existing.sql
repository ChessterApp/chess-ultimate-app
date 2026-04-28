-- Migration: Add nullable organization_id to existing tables
-- Phase 1: Foundation - Multi-Tenancy + RBAC
--
-- Strategy: Add column nullable first. Existing rows remain NULL (direct Chesster users).
-- RLS policies will check: organization_id IS NULL (direct users) OR org membership.

ALTER TABLE user_progress
  ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id);

CREATE INDEX IF NOT EXISTS idx_user_progress_org
  ON user_progress(organization_id);

ALTER TABLE lesson_chat_history
  ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id);

CREATE INDEX IF NOT EXISTS idx_lesson_chat_history_org
  ON lesson_chat_history(organization_id);

ALTER TABLE coaching_sessions
  ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id);

CREATE INDEX IF NOT EXISTS idx_coaching_sessions_org
  ON coaching_sessions(organization_id);

ALTER TABLE user_games
  ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id);

CREATE INDEX IF NOT EXISTS idx_user_games_org
  ON user_games(organization_id);

ALTER TABLE user_chess_profiles
  ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id);

CREATE INDEX IF NOT EXISTS idx_user_chess_profiles_org
  ON user_chess_profiles(organization_id);
