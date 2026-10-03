/**
 * POST /api/gamification/companion/attempts
 *   body: { assignment_id, submission: { uci? | placement? | fen? }, assistance_used? }
 *
 * Server validates the submitted move/answer with chess.js (move tasks) or an
 * exact placement match (setup tasks), records first-response correctness +
 * assistance, and writes evidence + mastery + the first-pass reward through ONE
 * idempotent RPC with a companion:* namespaced key. The response reports the
 * verdict and any reward — it NEVER contains the solution (plan A7). Behind both
 * companion flags; unlinked callers get 403. Attempting is never coin-gated (R1).
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { COMPANION_ENABLED } from '@/lib/feature-flags';
import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg } from '@/lib/companion/service';
import { recordAttempt } from '@/lib/companion/assessment-service';

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
  const submission =
    body?.submission && typeof body.submission === 'object' ? body.submission : null;
  if (!assignmentId || !submission) {
    return NextResponse.json({ error: 'assignment_id and submission required' }, { status: 400 });
  }

  const result = await recordAttempt({
    ownerUserId: r.ownerUserId,
    orgId: r.orgId,
    studentId: r.studentId,
    assignmentId,
    submission,
    assistanceUsed: body?.assistance_used === true,
  });

  if (result.status === 'not_found') {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }
  if (result.status === 'invalid_mode') {
    return NextResponse.json({ error: 'invalid_mode' }, { status: 409 });
  }
  return NextResponse.json(result, { status: 200 });
}
