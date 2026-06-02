-- Migration: Add Whop billing columns to organization_billing
-- Phase 1 — Self-Serve School Onboarding (PRD §6.1)
--
-- The existing organization_billing table is Stripe-shaped, but Whop is the
-- actual processor. We add nullable Whop columns alongside the Stripe ones
-- so any code still referencing Stripe keeps compiling. Stripe columns stay
-- null until/unless we ever wire Stripe.

ALTER TABLE organization_billing
  ADD COLUMN IF NOT EXISTS whop_membership_id TEXT,
  ADD COLUMN IF NOT EXISTS whop_user_id TEXT,
  ADD COLUMN IF NOT EXISTS whop_plan_id TEXT;

-- Backfill: keep the existing billing_cycle CHECK constraint as-is (already
-- accepts 'monthly' | 'annual' per migration 20260428_001).

-- Add a unique index on whop_membership_id so the webhook can safely upsert.
CREATE UNIQUE INDEX IF NOT EXISTS idx_org_billing_whop_membership
  ON organization_billing(whop_membership_id)
  WHERE whop_membership_id IS NOT NULL;

-- Add a unique index on organization_id so the webhook's onConflict works.
CREATE UNIQUE INDEX IF NOT EXISTS idx_org_billing_org_unique
  ON organization_billing(organization_id);

COMMENT ON COLUMN organization_billing.whop_membership_id IS
  'Whop membership ID returned from successful checkout. Source of truth for active org subscriptions.';
COMMENT ON COLUMN organization_billing.whop_user_id IS
  'Whop user ID — the Whop-side account that owns the membership.';
COMMENT ON COLUMN organization_billing.whop_plan_id IS
  'Whop plan ID (e.g. plan_xxxxx). Maps back to (tier, billing_cycle) via env vars.';
