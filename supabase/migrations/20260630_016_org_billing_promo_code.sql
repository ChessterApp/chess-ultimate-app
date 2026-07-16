-- Migration: Track which promo code (if any) an org redeemed at signup.
-- Source: docs/plans/WHITE_LABEL_PROMO_TASK.md T2.
--
-- Adds:
--   * organization_billing.redeemed_promo_code (TEXT) — code text, e.g. 'FREE'
--   * organization_billing.redeemed_promo_at (TIMESTAMPTZ)
--   * Partial index on redeemed_promo_code
--
-- Idempotent.

ALTER TABLE organization_billing
  ADD COLUMN IF NOT EXISTS redeemed_promo_code TEXT,
  ADD COLUMN IF NOT EXISTS redeemed_promo_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_org_billing_promo_code
  ON organization_billing (redeemed_promo_code)
  WHERE redeemed_promo_code IS NOT NULL;

COMMENT ON COLUMN organization_billing.redeemed_promo_code IS
  'Promo code redeemed at signup (e.g. ''FREE''). NULL for paid (Whop) flows.';
