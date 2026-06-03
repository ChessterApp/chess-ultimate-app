-- Migration: Multi-branch support for organizations (PRD §11.3 #2).
--
-- Adds `organization_branches` (one org → many branches) and an optional
-- `branch_id` foreign key on `organization_members` so a member can be
-- scoped to one branch. The `branch_admin` role is a new addition to the
-- existing role set (`owner | admin | teacher | student`) — branch admins
-- can manage members WITHIN their assigned branch but cannot see/edit
-- sibling-branch rows.
--
-- RLS:
--   - branch admins: read/write members in their own branch only.
--   - owner/admin: full org-scoped access (unchanged).
--   - sibling branch admin access is *denied* — covered by service-level
--     scoping in routes/admin.py + the RLS policy below.
--
-- Idempotent. Safe to re-run.

-- ─── Branches table ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS organization_branches (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  slug          TEXT NOT NULL,
  address       TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (organization_id, slug)
);

CREATE INDEX IF NOT EXISTS idx_org_branches_org
  ON organization_branches (organization_id);

-- ─── Member ↔ branch link ──────────────────────────────────────────────────

ALTER TABLE organization_members
  ADD COLUMN IF NOT EXISTS branch_id UUID
    REFERENCES organization_branches(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_org_members_branch
  ON organization_members (branch_id) WHERE branch_id IS NOT NULL;

-- ─── RLS ───────────────────────────────────────────────────────────────────

ALTER TABLE organization_branches ENABLE ROW LEVEL SECURITY;

-- Everyone in the org can read the branch list (used by the admin UI).
DROP POLICY IF EXISTS org_member_read_branches ON organization_branches;
CREATE POLICY org_member_read_branches ON organization_branches
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = organization_branches.organization_id
      AND om.user_id = auth.uid()::text
    )
  );

-- Only org-wide admins (owner/admin) can create/update/delete branches.
-- branch_admin role is scoped to MEMBERS, not branch metadata itself.
DROP POLICY IF EXISTS org_admin_manage_branches ON organization_branches;
CREATE POLICY org_admin_manage_branches ON organization_branches
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = organization_branches.organization_id
      AND om.user_id = auth.uid()::text
      AND om.role IN ('owner', 'admin')
    )
  );

-- branch admin scoping on organization_members: a branch_admin can only
-- see/modify rows whose branch_id matches their own branch_id. Org-wide
-- owner/admin policies remain unchanged.
DROP POLICY IF EXISTS branch_admin_manage_own_branch_members
  ON organization_members;
CREATE POLICY branch_admin_manage_own_branch_members ON organization_members
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM organization_members caller
      WHERE caller.organization_id = organization_members.organization_id
      AND caller.user_id = auth.uid()::text
      AND caller.role = 'branch_admin'
      AND caller.branch_id IS NOT NULL
      AND caller.branch_id = organization_members.branch_id
    )
  );

-- ROLLBACK (commented):
-- DROP POLICY IF EXISTS branch_admin_manage_own_branch_members ON organization_members;
-- DROP POLICY IF EXISTS org_admin_manage_branches ON organization_branches;
-- DROP POLICY IF EXISTS org_member_read_branches ON organization_branches;
-- ALTER TABLE organization_branches DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE organization_members DROP COLUMN branch_id;
-- DROP TABLE organization_branches;
