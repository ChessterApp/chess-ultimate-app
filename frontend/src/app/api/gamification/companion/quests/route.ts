/**
 * GET /api/gamification/companion/quests
 *   The quest strip: every active published quest with the owner's state
 *   (locked/available/active/objectives_complete/completed) + objective progress.
 *   Payloads carry copy keys only — NEVER a task solution (spec §7.2, plan A7).
 *   Completion is reconciled server-side from Watchtower evidence (idempotent);
 *   the first-completion reward commits at most once (companion:quest:* key).
 *
 * Behind both companion flags; unlinked callers get 403. Quests never gate any
 * educational path (R2) and are never coin-gated (R1).
 */
import 'server-only';
import { NextResponse } from 'next/server';
import { COMPANION_ENABLED } from '@/lib/feature-flags';
import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg } from '@/lib/companion/service';
import { loadQuests } from '@/lib/companion/quest-service';

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

  const quests = await loadQuests(r.ownerUserId, r.orgId, r.studentId);
  return NextResponse.json({ quests, count: quests.length }, { status: 200 });
}
