/**
 * POST /api/gamification/companion/reviews
 *   body: { assignment_id, submission: { uci? | squares? | placement? }, assistance_used? }
 *
 * The review-result path: server judges the submission (chess.js / set match),
 * advances the FIXED SM-2 ladder (1/3/7/14 — a miss resets to rung 1), and writes
 * evidence + mastery + the due_review reward through ONE idempotent RPC with a
 * companion:review:<owner>:<competency>:<marker> key. The response NEVER contains
 * the solution (plan A7). Behind both companion flags; unlinked callers get 403.
 * Reviewing is never coin-gated (R1).
 *
 * Issue a review assignment first via POST /assignments with { competency, mode:'review' }.
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { COMPANION_ENABLED } from '@/lib/feature-flags';
import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg } from '@/lib/companion/service';
import { recordReview } from '@/lib/companion/review-service';

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

  const result = await recordReview({
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
