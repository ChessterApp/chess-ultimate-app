-- ============================================================================
-- 20261013_051_parent_consent.sql
-- F8 (tracking plan T1) — parent/guardian consent captured at the end of the
-- consumer onboarding funnel ("I'm the parent/guardian and I agree to the
-- Terms & Privacy Policy").
--
-- Stored on user_onboarding (the row /api/onboarding/profile upserts, keyed by
-- clerk_user_id). Nullable: accounts that finished onboarding before this
-- change keep NULL and are never blocked.
--   parent_consent_at       when the parent ticked the box (server time)
--   parent_consent_version  which Terms/Privacy revision they agreed to
--
-- Additive + idempotent. Flask tolerates the columns being absent (the consent
-- write is a separate best-effort update), so code can ship before this is
-- applied. NOT applied to prod (separate approval step).
-- ============================================================================

ALTER TABLE user_onboarding
    ADD COLUMN IF NOT EXISTS parent_consent_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS parent_consent_version TEXT;
