-- Migration: refund automation (PRD §11.3 #4).
--
-- Two tables:
--   * organization_refunds — one row per Whop refund event. The
--     ``whop_event_id`` column is the idempotency key — repeated webhook
--     deliveries land on the same row (upsert), so replay never creates
--     duplicate refund records.
--   * organization_billing_audit — audit log for billing events
--     (refunds, plan changes, cancellations). Append-only from the app's
--     point of view (no delete/update API exposed). One log row per
--     idempotent refund-write (we look it up before insert).
--
-- Idempotent. Safe to re-run.

-- Add per-org last-refund stamp columns (used by the billing page summary).
ALTER TABLE organization_billing
  ADD COLUMN IF NOT EXISTS last_refund_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_refund_amount_cents INTEGER;

-- ─── Refunds ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS organization_refunds (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id   UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  whop_event_id     TEXT NOT NULL UNIQUE,
  whop_membership_id TEXT,
  amount_cents      INTEGER NOT NULL,
  currency          TEXT NOT NULL DEFAULT 'usd',
  reason            TEXT,
  status            TEXT NOT NULL DEFAULT 'processed',
  raw_payload       JSONB,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_org_refunds_org
  ON organization_refunds (organization_id);

-- ─── Billing audit log ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS organization_billing_audit (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id   UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  event_kind        TEXT NOT NULL,  -- 'refund' | 'plan_change' | 'canceled' | ...
  event_source_id   TEXT,            -- e.g. whop event id (for dedupe)
  payload           JSONB,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (event_kind, event_source_id)
);

CREATE INDEX IF NOT EXISTS idx_org_billing_audit_org
  ON organization_billing_audit (organization_id, created_at DESC);

-- ─── RLS ───────────────────────────────────────────────────────────────────

ALTER TABLE organization_refunds ENABLE ROW LEVEL SECURITY;
ALTER TABLE organization_billing_audit ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS org_owner_read_refunds ON organization_refunds;
CREATE POLICY org_owner_read_refunds ON organization_refunds
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = organization_refunds.organization_id
      AND om.user_id = auth.uid()::text
      AND om.role = 'owner'
    )
  );

DROP POLICY IF EXISTS org_owner_read_audit ON organization_billing_audit;
CREATE POLICY org_owner_read_audit ON organization_billing_audit
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = organization_billing_audit.organization_id
      AND om.user_id = auth.uid()::text
      AND om.role IN ('owner', 'admin')
    )
  );

-- ROLLBACK:
-- DROP POLICY IF EXISTS org_owner_read_audit ON organization_billing_audit;
-- DROP POLICY IF EXISTS org_owner_read_refunds ON organization_refunds;
-- DROP TABLE organization_billing_audit;
-- DROP TABLE organization_refunds;
