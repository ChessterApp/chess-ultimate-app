-- Migration: Branch-scoped invite tokens for external-school onboarding.
--
-- Phase 1 of the Chess Empire → Chesster onboarding arc. One token per
-- (org, external_branch_id) — distributed by the school manager to each
-- branch's parent group. The token authorizes the autocomplete + verify
-- flow scoped to that branch only.
--
-- Tokens are opaque (32 random bytes, base64url-encoded by the generator);
-- the table stores them as TEXT for index lookup. `revoked_at` allows
-- rotation without losing the audit trail.
--
-- Idempotent. Safe to re-run.

CREATE TABLE IF NOT EXISTS branch_invite_tokens (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  external_branch_id   UUID NOT NULL,
  branch_name          TEXT NOT NULL,
  token                TEXT NOT NULL UNIQUE,
  expires_at           TIMESTAMPTZ,
  revoked_at           TIMESTAMPTZ,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by           TEXT
);

CREATE INDEX IF NOT EXISTS idx_branch_invite_tokens_org_branch
  ON branch_invite_tokens (organization_id, external_branch_id);

CREATE INDEX IF NOT EXISTS idx_branch_invite_tokens_token
  ON branch_invite_tokens (token);

-- ─── RLS ───────────────────────────────────────────────────────────────────
-- Token resolution happens server-side via service role; no client direct
-- access. Restrictive policies enabled to fail closed.

ALTER TABLE branch_invite_tokens ENABLE ROW LEVEL SECURITY;

-- Org owners/admins can read tokens for their own org (admin panel display).
DROP POLICY IF EXISTS branch_invite_tokens_org_admin_read ON branch_invite_tokens;
CREATE POLICY branch_invite_tokens_org_admin_read ON branch_invite_tokens
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = branch_invite_tokens.organization_id
      AND om.user_id = auth.uid()::text
      AND om.role IN ('owner', 'admin')
    )
  );

-- ROLLBACK (commented):
-- DROP POLICY IF EXISTS branch_invite_tokens_org_admin_read ON branch_invite_tokens;
-- DROP INDEX IF EXISTS idx_branch_invite_tokens_token;
-- DROP INDEX IF EXISTS idx_branch_invite_tokens_org_branch;
-- DROP TABLE IF EXISTS branch_invite_tokens;
