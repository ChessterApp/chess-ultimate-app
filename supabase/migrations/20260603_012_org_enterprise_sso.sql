-- Migration: Enterprise self-serve flags (PRD §11.3 #1).
--
-- Adds nullable columns on `organizations` to record enterprise-specific
-- flags set during self-serve checkout:
--
--   * sso_enabled            BOOLEAN — toggle from the tier card
--   * sso_provider           TEXT    — set when admin configures SAML/OIDC
--                                      ('saml' | 'oidc' | NULL)
--   * sso_metadata           JSONB   — provider-specific config blob
--   * enterprise_activated_at TIMESTAMPTZ — stamped by the org-checkout webhook
--                                           when the enterprise plan goes live
--
-- The columns are intentionally nullable so non-enterprise orgs ignore them.
-- The actual SAML/OIDC flow is a stub (PRD §11.3 #1) — the schema reserves
-- the columns now so the wizard can store director intent without blocking
-- the rest of the rollout.

ALTER TABLE organizations
  ADD COLUMN IF NOT EXISTS sso_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS sso_provider TEXT,
  ADD COLUMN IF NOT EXISTS sso_metadata JSONB,
  ADD COLUMN IF NOT EXISTS enterprise_activated_at TIMESTAMPTZ;

-- Constrain sso_provider to known values when set
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'organizations_sso_provider_check'
  ) THEN
    ALTER TABLE organizations
      ADD CONSTRAINT organizations_sso_provider_check
      CHECK (sso_provider IS NULL OR sso_provider IN ('saml', 'oidc'));
  END IF;
END$$;

-- ROLLBACK:
-- ALTER TABLE organizations DROP CONSTRAINT IF EXISTS organizations_sso_provider_check;
-- ALTER TABLE organizations
--   DROP COLUMN IF EXISTS enterprise_activated_at,
--   DROP COLUMN IF EXISTS sso_metadata,
--   DROP COLUMN IF EXISTS sso_provider,
--   DROP COLUMN IF EXISTS sso_enabled;
