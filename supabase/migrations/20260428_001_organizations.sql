-- Migration: Create organization tables for multi-tenancy
-- Phase 1: Foundation - Multi-Tenancy + RBAC

-- Core tenant table
CREATE TABLE organizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  logo_url TEXT,
  favicon_url TEXT,
  primary_color TEXT DEFAULT '#1a73e8',
  secondary_color TEXT DEFAULT '#ffffff',
  accent_color TEXT DEFAULT '#ffd700',
  landing_page_config JSONB DEFAULT '{}',
  custom_css TEXT,
  contact_email TEXT,
  status TEXT DEFAULT 'active'
    CHECK (status IN ('active', 'suspended', 'trial')),
  trial_ends_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_organizations_slug ON organizations(slug);
CREATE INDEX idx_organizations_status ON organizations(status);

-- Org membership + roles
CREATE TABLE organization_members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'student'
    CHECK (role IN ('owner', 'admin', 'teacher', 'student')),
  invited_by TEXT,
  invited_at TIMESTAMPTZ,
  joined_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(organization_id, user_id)
);

CREATE INDEX idx_org_members_user ON organization_members(user_id);
CREATE INDEX idx_org_members_org ON organization_members(organization_id);

-- Content curation per org
CREATE TABLE organization_content (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  course_id UUID NOT NULL,
  visible BOOLEAN DEFAULT true,
  order_index INT DEFAULT 0,
  UNIQUE(organization_id, course_id)
);

CREATE INDEX idx_org_content_org ON organization_content(organization_id);

-- Per-seat billing
CREATE TABLE organization_billing (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  stripe_customer_id TEXT,
  stripe_subscription_id TEXT,
  plan TEXT DEFAULT 'starter'
    CHECK (plan IN ('starter', 'growth', 'enterprise')),
  student_count INT DEFAULT 0,
  price_per_student DECIMAL(10,2),
  billing_cycle TEXT DEFAULT 'monthly'
    CHECK (billing_cycle IN ('monthly', 'annual')),
  last_invoice_at TIMESTAMPTZ,
  next_invoice_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_org_billing_org ON organization_billing(organization_id);

-- Auto-update updated_at on organizations
CREATE OR REPLACE FUNCTION update_organizations_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_organizations_updated_at
  BEFORE UPDATE ON organizations
  FOR EACH ROW
  EXECUTE FUNCTION update_organizations_updated_at();
