-- ============================================================================
-- 20261013_054_drop_parent_consent.sql
-- Reverses 20261013_051_parent_consent.sql: the F8 parent/guardian consent
-- checkbox has been removed from onboarding, so its columns go too.
--
-- Columns verified empty in prod 2026-10-13. Idempotent (IF EXISTS), so it is
-- safe whether or not 051 was ever applied. NOT applied to prod (separate
-- approval step).
-- ============================================================================

ALTER TABLE user_onboarding
    DROP COLUMN IF EXISTS parent_consent_at,
    DROP COLUMN IF EXISTS parent_consent_version;
