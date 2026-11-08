/**
 * Resolve a public `/welcome/<branchToken>` invite token.
 *
 * Shared by the `/welcome/[branchToken]` page (heading + online copy) and its
 * JSON twin `GET /api/chess-empire/welcome/[branchToken]` (the mobile app).
 * Reads `branch_invite_tokens` via the service-role client; a missing, revoked
 * or expired token resolves to `null` ("link no longer valid").
 */
import 'server-only';
import { supabaseAdmin } from '@/lib/supabase-admin';

interface BranchTokenRow {
  organization_id: string;
  external_branch_id: string;
  branch_name: string;
  kind: string | null;
  expires_at: string | null;
  revoked_at: string | null;
}

export interface ResolvedToken {
  branchName: string;
  organizationId: string;
  externalBranchId: string;
  /** 'online' shows the CE Online copy + trial CTA; 'branch' (default) doesn't. */
  kind: 'branch' | 'online';
}

export async function resolveWelcomeToken(token: string): Promise<ResolvedToken | null> {
  if (!token) return null;
  const { data, error } = await supabaseAdmin
    .from('branch_invite_tokens')
    .select('organization_id, external_branch_id, branch_name, kind, expires_at, revoked_at')
    .eq('token', token)
    .maybeSingle();
  if (error || !data) return null;
  const row = data as BranchTokenRow;
  if (row.revoked_at) return null;
  if (row.expires_at && new Date(row.expires_at).getTime() < Date.now()) return null;
  return {
    branchName: row.branch_name,
    organizationId: row.organization_id,
    externalBranchId: row.external_branch_id,
    kind: row.kind === 'online' ? 'online' : 'branch',
  };
}
