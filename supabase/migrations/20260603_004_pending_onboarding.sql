-- Migration: pending_onboarding table for pre-payment wizard state
-- Phase 1 — Self-Serve School Onboarding (PRD §6.2)
--
-- Lets a director close the wizard tab and resume from the same step.
-- Promoted to organizations + organization_billing on payment success.

CREATE TABLE IF NOT EXISTS pending_onboarding (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clerk_user_id TEXT NOT NULL UNIQUE,
  email TEXT,
  step TEXT NOT NULL DEFAULT 'account',
  payload JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  expires_at TIMESTAMPTZ DEFAULT (now() + interval '24 hours')
);

CREATE INDEX IF NOT EXISTS idx_pending_onboarding_user
  ON pending_onboarding(clerk_user_id);

CREATE INDEX IF NOT EXISTS idx_pending_onboarding_expires
  ON pending_onboarding(expires_at);

-- Auto-bump updated_at
CREATE OR REPLACE FUNCTION update_pending_onboarding_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_pending_onboarding_updated_at ON pending_onboarding;
CREATE TRIGGER trigger_pending_onboarding_updated_at
  BEFORE UPDATE ON pending_onboarding
  FOR EACH ROW
  EXECUTE FUNCTION update_pending_onboarding_updated_at();
