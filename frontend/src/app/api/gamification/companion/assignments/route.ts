/**
 * POST /api/gamification/companion/assignments   body: { competency }
 *
 * Server selects a fresh assessment task instance for a competency and returns
 * its FEN + prompt. HARD RULE (plan A7): the response NEVER contains solution or
 * hint content — only the hint count. Behind both companion flags (UI kill-switch
 * + per-org server flag); unlinked callers get 403. No coins involved (R1).
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { COMPANION_ENABLED } from '@/lib/feature-flags';
import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg } from '@/lib/companion/service';
import { createAssignment } from '@/lib/companion/assessment-service';

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
  const competency = typeof body?.competency === 'string' ? body.competency : null;
  if (!competency) {
    return NextResponse.json({ error: 'competency required' }, { status: 400 });
  }

  const result = await createAssignment(r.ownerUserId, competency);
  if (result.status === 'no_tasks') {
    return NextResponse.json({ error: 'no_tasks' }, { status: 404 });
  }
  return NextResponse.json(result.task, { status: 200 });
}
