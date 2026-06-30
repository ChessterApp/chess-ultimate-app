import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { requireOrgAdmin } from '../../../_lib/guard';
import {
  freezeMember,
  unfreezeMember,
  OrgScopeError,
  NotFoundError,
} from '@/lib/chess-empire-admin';

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ orgId: string; memberId: string }> },
) {
  const { orgId, memberId } = await params;
  const guard = await requireOrgAdmin(orgId);
  if (!guard.ok) return guard.response;

  const body = (await req.json().catch(() => ({}))) as { unfreeze?: unknown };
  const unfreeze = body.unfreeze === true;

  try {
    const member = unfreeze
      ? await unfreezeMember({
          orgId,
          memberId,
          actorClerkUserId: guard.userId,
        })
      : await freezeMember({
          orgId,
          memberId,
          actorClerkUserId: guard.userId,
        });
    return NextResponse.json({ member, frozen: !unfreeze });
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
