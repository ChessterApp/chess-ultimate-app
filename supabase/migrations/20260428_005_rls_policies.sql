-- Migration: RLS policies for all org-scoped tables
-- Phase 1: Foundation - Multi-Tenancy + RBAC
--
-- Pattern:
--   direct_user_access: org_id IS NULL AND user owns the row
--   org_member_access: org_id IS NOT NULL AND user is a member of that org
--   org_admin_access: org_id IS NOT NULL AND user is owner/admin/teacher in that org

-- ============================================
-- Enable RLS on new organization tables
-- ============================================

ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE organization_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE organization_content ENABLE ROW LEVEL SECURITY;
ALTER TABLE organization_billing ENABLE ROW LEVEL SECURITY;

-- Organizations: anyone can read active orgs (for subdomain resolution)
CREATE POLICY "public_read_active_orgs" ON organizations
  FOR SELECT
  USING (status = 'active');

-- Organizations: only owners/admins can update their org
CREATE POLICY "org_admin_update" ON organizations
  FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = organizations.id
      AND om.user_id = auth.uid()::text
      AND om.role IN ('owner', 'admin')
    )
  );

-- Organization members: members can see other members in their org
CREATE POLICY "org_members_read" ON organization_members
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = organization_members.organization_id
      AND om.user_id = auth.uid()::text
    )
  );

-- Organization members: only owners/admins can insert/update/delete members
CREATE POLICY "org_admin_manage_members" ON organization_members
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = organization_members.organization_id
      AND om.user_id = auth.uid()::text
      AND om.role IN ('owner', 'admin')
    )
  );

-- Organization content: members can read content for their org
CREATE POLICY "org_member_read_content" ON organization_content
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = organization_content.organization_id
      AND om.user_id = auth.uid()::text
    )
  );

-- Organization content: only owners/admins can manage content curation
CREATE POLICY "org_admin_manage_content" ON organization_content
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = organization_content.organization_id
      AND om.user_id = auth.uid()::text
      AND om.role IN ('owner', 'admin')
    )
  );

-- Organization billing: only owners can see billing
CREATE POLICY "org_owner_billing" ON organization_billing
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = organization_billing.organization_id
      AND om.user_id = auth.uid()::text
      AND om.role = 'owner'
    )
  );

-- ============================================
-- Enable RLS on existing tables (if not already)
-- ============================================

ALTER TABLE user_progress ENABLE ROW LEVEL SECURITY;
ALTER TABLE lesson_chat_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE coaching_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_games ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_chess_profiles ENABLE ROW LEVEL SECURITY;

-- ============================================
-- user_progress RLS
-- ============================================

CREATE POLICY "direct_user_access" ON user_progress
  FOR ALL
  USING (organization_id IS NULL AND user_id = auth.uid()::text);

CREATE POLICY "org_member_access" ON user_progress
  FOR ALL
  USING (
    organization_id IS NOT NULL
    AND user_id = auth.uid()::text
    AND EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = user_progress.organization_id
      AND om.user_id = auth.uid()::text
    )
  );

CREATE POLICY "org_admin_access" ON user_progress
  FOR SELECT
  USING (
    organization_id IS NOT NULL
    AND EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = user_progress.organization_id
      AND om.user_id = auth.uid()::text
      AND om.role IN ('owner', 'admin', 'teacher')
    )
  );

-- ============================================
-- lesson_chat_history RLS
-- ============================================

CREATE POLICY "direct_user_access" ON lesson_chat_history
  FOR ALL
  USING (organization_id IS NULL AND user_id = auth.uid()::text);

CREATE POLICY "org_member_access" ON lesson_chat_history
  FOR ALL
  USING (
    organization_id IS NOT NULL
    AND user_id = auth.uid()::text
    AND EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = lesson_chat_history.organization_id
      AND om.user_id = auth.uid()::text
    )
  );

CREATE POLICY "org_admin_access" ON lesson_chat_history
  FOR SELECT
  USING (
    organization_id IS NOT NULL
    AND EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = lesson_chat_history.organization_id
      AND om.user_id = auth.uid()::text
      AND om.role IN ('owner', 'admin', 'teacher')
    )
  );

-- ============================================
-- coaching_sessions RLS
-- ============================================

CREATE POLICY "direct_user_access" ON coaching_sessions
  FOR ALL
  USING (organization_id IS NULL AND user_id = auth.uid()::text);

CREATE POLICY "org_member_access" ON coaching_sessions
  FOR ALL
  USING (
    organization_id IS NOT NULL
    AND user_id = auth.uid()::text
    AND EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = coaching_sessions.organization_id
      AND om.user_id = auth.uid()::text
    )
  );

CREATE POLICY "org_admin_access" ON coaching_sessions
  FOR SELECT
  USING (
    organization_id IS NOT NULL
    AND EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = coaching_sessions.organization_id
      AND om.user_id = auth.uid()::text
      AND om.role IN ('owner', 'admin', 'teacher')
    )
  );

-- ============================================
-- user_games RLS
-- ============================================

CREATE POLICY "direct_user_access" ON user_games
  FOR ALL
  USING (organization_id IS NULL AND user_id = auth.uid()::text);

CREATE POLICY "org_member_access" ON user_games
  FOR ALL
  USING (
    organization_id IS NOT NULL
    AND user_id = auth.uid()::text
    AND EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = user_games.organization_id
      AND om.user_id = auth.uid()::text
    )
  );

CREATE POLICY "org_admin_access" ON user_games
  FOR SELECT
  USING (
    organization_id IS NOT NULL
    AND EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = user_games.organization_id
      AND om.user_id = auth.uid()::text
      AND om.role IN ('owner', 'admin', 'teacher')
    )
  );

-- ============================================
-- user_chess_profiles RLS
-- ============================================

CREATE POLICY "direct_user_access" ON user_chess_profiles
  FOR ALL
  USING (organization_id IS NULL AND user_id = auth.uid()::text);

CREATE POLICY "org_member_access" ON user_chess_profiles
  FOR ALL
  USING (
    organization_id IS NOT NULL
    AND user_id = auth.uid()::text
    AND EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = user_chess_profiles.organization_id
      AND om.user_id = auth.uid()::text
    )
  );

CREATE POLICY "org_admin_access" ON user_chess_profiles
  FOR SELECT
  USING (
    organization_id IS NOT NULL
    AND EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = user_chess_profiles.organization_id
      AND om.user_id = auth.uid()::text
      AND om.role IN ('owner', 'admin', 'teacher')
    )
  );
