-- Migration: Ownership-transfer state machine (PRD §11.3 #3 / §7 edge case).
--
-- A director can hand off ownership to an assistant (or another existing
-- admin) via /admin/settings/team. The transfer is a 4-state machine:
--
--   invite_pending  → newly-created token, invitee not yet acted
--   accepted        → invitee accepted; awaiting owner re-confirmation
--   revoked         → owner canceled the transfer (terminal)
--   expired         → token aged past its TTL with no action (terminal)
--
-- After accepted + owner re-confirmation in /admin/settings/team, the
-- backend swaps the `owner` role on organization_members and stamps
-- `completed_at` (the row stays for audit; it does not re-transition).
--
-- The state transitions are enforced by `services.ownership_transfer`.
-- The DB only stores the current state + audit fields.

CREATE TABLE IF NOT EXISTS organization_ownership_transfers (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id   UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  current_owner_user_id  TEXT NOT NULL,
  invitee_email     TEXT NOT NULL,
  invitee_user_id   TEXT,
  token             TEXT NOT NULL UNIQUE,
  state             TEXT NOT NULL CHECK (state IN (
    'invite_pending', 'accepted', 'revoked', 'expired', 'completed'
  )),
  expires_at        TIMESTAMPTZ NOT NULL,
  accepted_at       TIMESTAMPTZ,
  revoked_at        TIMESTAMPTZ,
  completed_at      TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ownership_transfers_org
  ON organization_ownership_transfers (organization_id);

CREATE INDEX IF NOT EXISTS idx_ownership_transfers_state
  ON organization_ownership_transfers (state)
  WHERE state IN ('invite_pending', 'accepted');

-- RLS
ALTER TABLE organization_ownership_transfers ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS owner_manage_transfers ON organization_ownership_transfers;
CREATE POLICY owner_manage_transfers ON organization_ownership_transfers
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = organization_ownership_transfers.organization_id
      AND om.user_id = auth.uid()::text
      AND om.role = 'owner'
    )
  );

-- ROLLBACK:
-- DROP POLICY IF EXISTS owner_manage_transfers ON organization_ownership_transfers;
-- DROP TABLE organization_ownership_transfers;
