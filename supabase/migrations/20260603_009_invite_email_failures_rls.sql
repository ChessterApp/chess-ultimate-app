-- Migration: enable RLS on invite_email_failures (Phase-1 carryover surfaced
-- by test_rls_cross_org_fuzzer in Phase 2).
--
-- The fuzzer flagged ``invite_email_failures`` (added in
-- 20260603_005_invite_email_failures.sql) as an org-scoped table without
-- RLS. This migration:
--   * enables RLS on the table,
--   * adds a service-role-only policy (the table is operational/telemetry —
--     tenants do not need read access; service role bypasses RLS anyway,
--     so this is effectively deny-all-for-tenants).
--
-- Idempotent. Safe to re-run.

ALTER TABLE invite_email_failures ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS invite_email_failures_service_only
    ON invite_email_failures;
CREATE POLICY invite_email_failures_service_only
    ON invite_email_failures
    FOR ALL USING (false) WITH CHECK (false);

-- ROLLBACK (commented; copy-paste to revert):
-- DROP POLICY IF EXISTS invite_email_failures_service_only ON invite_email_failures;
-- ALTER TABLE invite_email_failures DISABLE ROW LEVEL SECURITY;
