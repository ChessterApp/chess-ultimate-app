-- Migration: Platform super-admin foundations (Phase 7A)
-- Adds tables to support the /super-admin dashboard:
--   - platform_admin_audit_log: every super-admin action is logged
--   - impersonation_sessions: read-only "view as user" sessions
--   - platform_user_status: suspend/ban state per Clerk user
--   - platform_user_cache: denormalised search index across Clerk + Whop + Supabase
--   - feature_flags: gradual feature rollouts (parked for 7D, schema lands now)

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ─── Audit log ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS platform_admin_audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  admin_clerk_id TEXT NOT NULL,
  action TEXT NOT NULL,
  target_type TEXT NOT NULL CHECK (target_type IN ('user', 'organization', 'system')),
  target_id TEXT NOT NULL,
  payload JSONB,
  ip_address INET,
  user_agent TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_admin
  ON platform_admin_audit_log(admin_clerk_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_target
  ON platform_admin_audit_log(target_type, target_id, created_at DESC);

-- The audit log must be append-only — no UPDATE/DELETE (enforced at the
-- service-role boundary; we add a trigger as belt-and-braces).
CREATE OR REPLACE FUNCTION reject_audit_log_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'platform_admin_audit_log is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_log_no_update ON platform_admin_audit_log;
CREATE TRIGGER audit_log_no_update
  BEFORE UPDATE OR DELETE ON platform_admin_audit_log
  FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();

-- ─── Impersonation sessions ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS impersonation_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  admin_clerk_id TEXT NOT NULL,
  target_clerk_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  ended_at TIMESTAMPTZ,
  ip_address INET
);

CREATE INDEX IF NOT EXISTS idx_impersonation_admin
  ON impersonation_sessions(admin_clerk_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_impersonation_target
  ON impersonation_sessions(target_clerk_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_impersonation_active
  ON impersonation_sessions(started_at DESC) WHERE ended_at IS NULL;

-- ─── Platform user status (suspend/ban/delete state) ───────────────────────
CREATE TABLE IF NOT EXISTS platform_user_status (
  clerk_id TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'suspended', 'banned', 'deleted')),
  suspended_reason TEXT,
  suspended_at TIMESTAMPTZ,
  suspended_by TEXT,
  notes TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION update_platform_user_status_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_platform_user_status_updated_at ON platform_user_status;
CREATE TRIGGER trigger_platform_user_status_updated_at
  BEFORE UPDATE ON platform_user_status
  FOR EACH ROW EXECUTE FUNCTION update_platform_user_status_updated_at();

-- ─── Platform user cache (search index) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS platform_user_cache (
  clerk_id TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  name TEXT,
  signup_at TIMESTAMPTZ,
  last_seen_at TIMESTAMPTZ,
  subscription_status TEXT,
  whop_membership_id TEXT,
  org_count INT DEFAULT 0,
  total_revenue_cents INT DEFAULT 0,
  refreshed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_cache_email_trgm
  ON platform_user_cache USING gin (email gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_user_cache_name_trgm
  ON platform_user_cache USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_user_cache_status
  ON platform_user_cache(subscription_status);
CREATE INDEX IF NOT EXISTS idx_user_cache_signup
  ON platform_user_cache(signup_at DESC);

-- ─── Feature flags (Phase 7D — schema only) ────────────────────────────────
CREATE TABLE IF NOT EXISTS feature_flags (
  key TEXT PRIMARY KEY,
  enabled BOOLEAN DEFAULT FALSE,
  rollout_percent INT DEFAULT 0 CHECK (rollout_percent >= 0 AND rollout_percent <= 100),
  allowlist_clerk_ids TEXT[] DEFAULT '{}',
  allowlist_org_ids UUID[] DEFAULT '{}',
  description TEXT,
  updated_by TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION update_feature_flags_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_feature_flags_updated_at ON feature_flags;
CREATE TRIGGER trigger_feature_flags_updated_at
  BEFORE UPDATE ON feature_flags
  FOR EACH ROW EXECUTE FUNCTION update_feature_flags_updated_at();

-- ─── RLS — service-role only ───────────────────────────────────────────────
-- Every table is locked down: only the Supabase service role (used by the
-- Flask backend) may read/write. Direct Postgrest access from the browser
-- using anon/authenticated keys will be denied.
ALTER TABLE platform_admin_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE impersonation_sessions    ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform_user_status      ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform_user_cache       ENABLE ROW LEVEL SECURITY;
ALTER TABLE feature_flags             ENABLE ROW LEVEL SECURITY;

-- No policies → default deny for non-service-role connections.
