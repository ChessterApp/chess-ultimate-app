/**
 * GET   /api/gamification/companion/goal
 *   Returns the owner's weekly practice-days goal: target + current-week progress
 *   (distinct meaningful days) + week bounds. NO solution/PII.
 *
 * PATCH /api/gamification/companion/goal
 *   body: { target: 1..7 } — update the user-adjustable target (bounds validated).
 *
 * The weekly goal is informational only — it NEVER gates or unlocks anything and
 * a missed week has no penalty (R2). Behind both companion flags (UI kill-switch
 * + per-org server flag); unlinked callers get 403. Never coin-gated (R1).
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { COMPANION_ENABLED } from '@/lib/feature-flags';
import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg } from '@/lib/companion/service';
import { loadGoal, setGoalTarget } from '@/lib/companion/goal-service';

export const dynamic = 'force-dynamic';

export async function GET() {
  if (!COMPANION_ENABLED) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }

  const r = await resolveStudent();
  if (!r.ok) return NextResponse.json({ error: r.error }, { status: r.status });

  if (!(await isCompanionEnabledForOrg(r.orgId))) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }

  const goal = await loadGoal(r.ownerUserId);
  return NextResponse.json(goal, { status: 200 });
}

export async function PATCH(req: NextRequest) {
  if (!COMPANION_ENABLED) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }

  const r = await resolveStudent();
  if (!r.ok) return NextResponse.json({ error: r.error }, { status: r.status });

  if (!(await isCompanionEnabledForOrg(r.orgId))) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }

  const body = await req.json().catch(() => ({}));
  const result = await setGoalTarget(r.ownerUserId, body?.target);
  if (result.status === 'invalid_target') {
    return NextResponse.json({ error: 'invalid_target' }, { status: 400 });
  }
  return NextResponse.json(result.goal, { status: 200 });
}
