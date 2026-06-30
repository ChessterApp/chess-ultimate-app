/**
 * Chess Empire branch-invite token index.
 *
 *  - GET:  list all tokens (active + revoked) for an org.
 *  - POST: insert a new active token for a branch that has none yet.
 *          Returns 409 `existing_active_token` if a non-revoked token
 *          already exists for that `external_branch_id`.
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { requireOrgAdmin } from '../_lib/guard';
import {
  listBranchTokens,
  insertBranchToken,
  ExistingActiveTokenError,
} from '@/lib/chess-empire-admin';

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ orgId: string }> },
) {
  const { orgId } = await params;
  const guard = await requireOrgAdmin(orgId);
  if (!guard.ok) return guard.response;
  try {
    const tokens = await listBranchTokens(orgId);
    return NextResponse.json({ tokens });
  } catch {
    return NextResponse.json({ error: 'internal_error' }, { status: 500 });
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ orgId: string }> },
) {
  const { orgId } = await params;
  const guard = await requireOrgAdmin(orgId);
  if (!guard.ok) return guard.response;

  const body = (await req.json().catch(() => ({}))) as {
    branchId?: unknown;
    branchName?: unknown;
  };
  const branchId = typeof body.branchId === 'string' ? body.branchId : '';
  const branchName = typeof body.branchName === 'string' ? body.branchName : '';
  if (!branchId || !branchName) {
    return NextResponse.json({ error: 'missing_branch' }, { status: 400 });
  }

  try {
    const created = await insertBranchToken({
      orgId,
      branchId,
      branchName,
      actorClerkUserId: guard.userId,
    });
    const url = `https://chess-empire.chesster.io/welcome/${created.token}`;
    return NextResponse.json({ created, url }, { status: 201 });
  } catch (err) {
    if (err instanceof ExistingActiveTokenError) {
      return NextResponse.json(
        { error: 'existing_active_token' },
        { status: 409 },
      );
    }
    return NextResponse.json({ error: 'internal_error' }, { status: 500 });
  }
}
