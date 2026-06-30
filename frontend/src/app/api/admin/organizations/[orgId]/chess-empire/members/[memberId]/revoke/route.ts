import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { requireOrgAdmin } from '../../../_lib/guard';
import {
  revokeMember,
  OrgScopeError,
  NotFoundError,
} from '@/lib/chess-empire-admin';

export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ orgId: string; memberId: string }> },
) {
  const { orgId, memberId } = await params;
  const guard = await requireOrgAdmin(orgId);
  if (!guard.ok) return guard.response;

  try {
    const member = await revokeMember({
      orgId,
      memberId,
      actorClerkUserId: guard.userId,
    });
    return NextResponse.json({ member });
  } catch (err) {
    if (err instanceof OrgScopeError) {
      return NextResponse.json({ error: 'forbidden' }, { status: 403 });
    }
    if (err instanceof NotFoundError) {
      return NextResponse.json({ error: 'member_not_found' }, { status: 404 });
    }
    return NextResponse.json({ error: 'internal_error' }, { status: 500 });
  }
}
