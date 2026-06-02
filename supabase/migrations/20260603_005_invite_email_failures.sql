-- Migration: invite_email_failures for retry visibility
-- Phase 1 — Self-Serve School Onboarding (PRD §6.4)
--
-- When Resend send fails, we log the row here so ops can retry / inspect.
-- We never block the invite-create flow on email failure.

CREATE TABLE IF NOT EXISTS invite_email_failures (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  to_email TEXT NOT NULL,
  role TEXT,
  error_message TEXT NOT NULL,
  retry_count INT NOT NULL DEFAULT 0,
  last_attempt_at TIMESTAMPTZ DEFAULT now(),
  resolved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_invite_email_failures_unresolved
  ON invite_email_failures(organization_id, resolved_at)
  WHERE resolved_at IS NULL;
