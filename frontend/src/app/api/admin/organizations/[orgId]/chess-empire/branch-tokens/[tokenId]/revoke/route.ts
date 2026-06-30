import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { requireOrgAdmin } from '../../../_lib/guard';
import {
  revokeBranchToken,
  OrgScopeError,
  NotFoundError,
} from '@/lib/chess-empire-admin';

export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ orgId: string; tokenId: string }> },
) {
  const { orgId, tokenId } = await params;
  const guard = await requireOrgAdmin(orgId);
  if (!guard.ok) return guard.response;

  try {
    const revoked = await revokeBranchToken({
      orgId,
      tokenId,
      actorClerkUserId: guard.userId,
    });
    return NextResponse.json({ revoked });
  } catch (err) {
    if (err instanceof OrgScopeError) {
      return NextResponse.json({ error: 'forbidden' }, { status: 403 });
    }
    if (err instanceof NotFoundError) {
      return NextResponse.json({ error: 'token_not_found' }, { status: 404 });
    }
    return NextResponse.json({ error: 'internal_error' }, { status: 500 });
  }
}
