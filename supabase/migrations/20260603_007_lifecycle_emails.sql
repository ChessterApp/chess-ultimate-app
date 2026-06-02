-- Migration: lifecycle_emails — outbound scheduling table (PRD §11.2 #6).
--
-- Each row represents one *scheduled* lifecycle email for one organization.
-- The CLI command `flask lifecycle-emails send-due` reads rows where
-- ``scheduled_for <= now()`` and ``sent_at IS NULL``, attempts delivery, and
-- updates the row in place. Failures store the error text for retry
-- visibility (matches the pattern used by invite_email_failures).
--
-- Kinds (controlled vocabulary — keep in sync with services/lifecycle_emails.py):
--   * welcome_day1   — Day 1: welcome + checklist
--   * nudge_day3     — Day 3: nudge unfinished onboarding items
--   * success_day7   — Day 7: success story / upgrade prompt
--   * custom_domain_active  — terminal-state notification (custom domain)
--   * custom_domain_failed
--
-- Idempotent: IF NOT EXISTS guards. Safe to re-run.

CREATE TABLE IF NOT EXISTS lifecycle_emails (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL,
    scheduled_for TIMESTAMPTZ NOT NULL,
    sent_at       TIMESTAMPTZ,
    error         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lifecycle_due
    ON lifecycle_emails (scheduled_for)
    WHERE sent_at IS NULL;

-- One org cannot receive the same scheduled kind twice (insert-on-conflict
-- becomes a no-op when the scheduler is re-run for the same org).
CREATE UNIQUE INDEX IF NOT EXISTS idx_lifecycle_org_kind
    ON lifecycle_emails (org_id, kind);

-- RLS: only the service-role / super-admin should see lifecycle rows.
-- Tenants don't need to query this table directly.
ALTER TABLE lifecycle_emails ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS lifecycle_emails_service_only ON lifecycle_emails;
CREATE POLICY lifecycle_emails_service_only ON lifecycle_emails
    FOR ALL USING (false) WITH CHECK (false);

-- ROLLBACK (commented; copy-paste to revert):
-- DROP POLICY IF EXISTS lifecycle_emails_service_only ON lifecycle_emails;
-- DROP INDEX IF EXISTS idx_lifecycle_org_kind;
-- DROP INDEX IF EXISTS idx_lifecycle_due;
-- DROP TABLE IF EXISTS lifecycle_emails;
