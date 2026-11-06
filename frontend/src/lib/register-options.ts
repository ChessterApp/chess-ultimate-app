/**
 * Register picker options — the org's active branch-invite tokens.
 *
 * Shared by the public `/register` page and its JSON twin
 * `GET /api/chess-empire/register/options` (the mobile app's registration
 * entry). Reads `branch_invite_tokens` for the org via the service-role client,
 * drops revoked/expired rows, and dedupes to the newest token per branch plus
 * the newest online-kind token. The page already renders every returned token
 * as a public `/welcome/<token>` link.
 */
import 'server-only';
import { supabaseAdmin } from '@/lib/supabase-admin';
import type { RegisterOption } from '@/app/register/RegisterPicker';

export type { RegisterOption };

interface TokenRow {
  token: string;
  external_branch_id: string;
  branch_name: string;
  kind: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string | null;
}

export interface RegisterOptions {
  branches: RegisterOption[];
  online: RegisterOption | null;
}

/**
 * Resolve the org's active branch-invite tokens into picker options.
 * Filters out revoked/expired tokens, then dedupes to the newest token per
 * branch (and the newest online-kind token overall).
 */
export async function loadRegisterOptions(orgId: string): Promise<RegisterOptions> {
  const { data, error } = await supabaseAdmin
    .from('branch_invite_tokens')
    .select('token, external_branch_id, branch_name, kind, expires_at, revoked_at, created_at')
    .eq('organization_id', orgId);

  if (error || !data) return { branches: [], online: null };

  const now = Date.now();
  const active = (data as TokenRow[]).filter((row) => {
    if (row.revoked_at) return false;
    if (row.expires_at && new Date(row.expires_at).getTime() < now) return false;
    return true;
  });

  // Newest first so the first row seen per branch is the freshest token.
  active.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));

  const seen = new Set<string>();
  const branches: RegisterOption[] = [];
  let online: RegisterOption | null = null;

  for (const row of active) {
    if (row.kind === 'online') {
      if (!online) online = { token: row.token, branchName: row.branch_name };
      continue;
    }
    if (seen.has(row.external_branch_id)) continue;
    seen.add(row.external_branch_id);
    branches.push({ token: row.token, branchName: row.branch_name });
  }

  return { branches, online };
}
