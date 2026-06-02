-- Migration: organization_billing prorate columns (PRD §11.2 #8 — Phase 2).
--
-- Captures the next charge amount Whop reports for an annual plan that
-- changed mid-cycle, and the cancellation timestamp when the director
-- cancels a subscription.
--
-- Idempotent: IF NOT EXISTS guards. Safe to re-run.

ALTER TABLE organization_billing
  ADD COLUMN IF NOT EXISTS next_charge_amount_cents INTEGER,
  ADD COLUMN IF NOT EXISTS canceled_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_org_billing_canceled_at
  ON organization_billing (canceled_at)
  WHERE canceled_at IS NOT NULL;

-- ROLLBACK (commented; copy-paste to revert):
-- DROP INDEX IF EXISTS idx_org_billing_canceled_at;
-- ALTER TABLE organization_billing DROP COLUMN IF EXISTS canceled_at;
-- ALTER TABLE organization_billing DROP COLUMN IF EXISTS next_charge_amount_cents;
