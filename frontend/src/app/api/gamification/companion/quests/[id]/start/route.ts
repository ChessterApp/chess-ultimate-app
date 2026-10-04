/**
 * POST /api/gamification/companion/quests/:id/start
 *   Move a quest available → active (records started_at) for the resolved owner,
 *   then reconcile completion server-side (if objectives are already met the
 *   first-completion reward commits once, idempotently). Returns the quest view;
 *   NEVER echoes a task solution.
 *
 * Behind both companion flags; unlinked callers get 403. 404 for an unknown
 * quest id. Quests never gate any educational path (R2); never coin-gated (R1).
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { COMPANION_ENABLED } from '@/lib/feature-flags';
import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg } from '@/lib/companion/service';
import { startQuest } from '@/lib/companion/quest-service';

export const dynamic = 'force-dynamic';

export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  if (!COMPANION_ENABLED) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }

  const r = await resolveStudent();
  if (!r.ok) return NextResponse.json({ error: r.error }, { status: r.status });

  if (!(await isCompanionEnabledForOrg(r.orgId))) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }

  const { id } = await params;
  if (!id) return NextResponse.json({ error: 'quest id required' }, { status: 400 });

  const result = await startQuest({
    ownerUserId: r.ownerUserId,
    orgId: r.orgId,
    studentId: r.studentId,
    questId: id,
  });
  if (result.status === 'not_found') {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }
  return NextResponse.json(result.quest, { status: 200 });
}
