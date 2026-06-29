-- Migration: Promo code table for partner-school onboarding (PROMO_CODE_PRD §1).
--
-- Adds a single-table promo-code store used by /for-schools/start/payment to
-- bypass Whop checkout for 100%-off codes. v1 supports 100%-off codes only;
-- partial discounts are validated server-side in the redeem endpoint.

CREATE TABLE IF NOT EXISTS promo_codes (
  code         TEXT PRIMARY KEY,
  discount_pct INT NOT NULL CHECK (discount_pct BETWEEN 1 AND 100),
  max_uses     INT,
  uses         INT NOT NULL DEFAULT 0,
  active       BOOLEAN NOT NULL DEFAULT TRUE,
  expires_at   TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed v1 launch code.
INSERT INTO promo_codes (code, discount_pct, max_uses, active)
VALUES ('FREE', 100, NULL, TRUE)
ON CONFLICT (code) DO NOTHING;

-- ROLLBACK:
-- DROP TABLE promo_codes;
