/**
 * GET /api/admin/organizations/[orgId]/chess-empire/unlinked
 *
 * Org-admin-gated. Returns the list of orphan Clerk users in the org (no
 * verified organization_members row) together with their most recent
 * link_attempts, so the admin can pick each one and manually link to a
 * student via the sibling POST /link endpoint.
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { requireOrgAdmin } from '../_lib/guard';
import { listUnlinkedUsers } from '@/lib/chess-empire-admin';

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ orgId: string }> },
) {
  const { orgId } = await params;
  const guard = await requireOrgAdmin(orgId);
  if (!guard.ok) return guard.response;

  try {
    const payload = await listUnlinkedUsers(orgId);
    return NextResponse.json(payload);
  } catch (err) {
    console.error('[unlinked] failed', err);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }
}
