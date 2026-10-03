/**
 * POST /api/gamification/companion/hints   body: { assignment_id, hint_index? }
 *
 * Logs assistance (sets assistance_used on the assignment) BEFORE revealing the
 * hint content — so a hinted attempt can never score as independent demonstration
 * evidence (spec §4.3, §12.3). Behind both companion flags; unlinked callers get
 * 403. Hints are always free — nothing educational is coin-gated (R1).
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { COMPANION_ENABLED } from '@/lib/feature-flags';
import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg } from '@/lib/companion/service';
import { logHint } from '@/lib/companion/assessment-service';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  if (!COMPANION_ENABLED) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }

  const r = await resolveStudent();
  if (!r.ok) return NextResponse.json({ error: r.error }, { status: r.status });

  if (!(await isCompanionEnabledForOrg(r.orgId))) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }

  const body = await req.json().catch(() => ({}));
  const assignmentId = typeof body?.assignment_id === 'string' ? body.assignment_id : null;
  if (!assignmentId) {
    return NextResponse.json({ error: 'assignment_id required' }, { status: 400 });
  }
  const hintIndex = Number.isFinite(body?.hint_index) ? Number(body.hint_index) : 0;

  const result = await logHint(r.ownerUserId, assignmentId, hintIndex);
  if (result.status === 'not_found') {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }
  return NextResponse.json(result, { status: 200 });
}
