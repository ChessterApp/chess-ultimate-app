/**
 * PATCH /api/admin/organizations/[orgId]/chess-empire/members/[memberId]/access
 *
 * Org-admin-gated. Sets an online trial member's access window. Body:
 * `{ "accessExpiresAt": "<ISO string>" | null }` — `null` upgrades to full
 * (permanent) access; an ISO string (past or future) moves the trial expiry.
 * Rejects non-`online` members (403) — roster access is managed by CE.
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { requireOrgAdmin } from '../../../_lib/guard';
import {
  setMemberAccessExpiry,
  OrgScopeError,
  NotFoundError,
  NotOnlineMemberError,
} from '@/lib/chess-empire-admin';

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ orgId: string; memberId: string }> },
) {
  const { orgId, memberId } = await params;
  const guard = await requireOrgAdmin(orgId);
  if (!guard.ok) return guard.response;

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'bad_json' }, { status: 400 });
  }
  if (
    typeof body !== 'object' ||
    body === null ||
    !('accessExpiresAt' in body)
  ) {
    return NextResponse.json({ error: 'invalid_body' }, { status: 400 });
  }

  const raw = (body as { accessExpiresAt: unknown }).accessExpiresAt;
  let accessExpiresAt: string | null;
  if (raw === null) {
    accessExpiresAt = null;
  } else if (typeof raw === 'string') {
    const ms = Date.parse(raw);
    if (Number.isNaN(ms)) {
      return NextResponse.json({ error: 'invalid_date' }, { status: 400 });
    }
    accessExpiresAt = new Date(ms).toISOString();
  } else {
    return NextResponse.json({ error: 'invalid_body' }, { status: 400 });
  }

  try {
    const member = await setMemberAccessExpiry({
      orgId,
      memberId,
      accessExpiresAt,
      actorClerkUserId: guard.userId,
    });
    return NextResponse.json({ member });
  } catch (err) {
    if (err instanceof OrgScopeError) {
      return NextResponse.json({ error: 'forbidden' }, { status: 403 });
    }
    if (err instanceof NotOnlineMemberError) {
      return NextResponse.json({ error: 'not_online_member' }, { status: 403 });
    }
    if (err instanceof NotFoundError) {
      return NextResponse.json({ error: 'member_not_found' }, { status: 404 });
    }
    return NextResponse.json({ error: 'internal_error' }, { status: 500 });
  }
}
