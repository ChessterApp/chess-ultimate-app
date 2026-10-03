/**
 * GET  /api/gamification/companion/watchtower
 *   The Watchtower chapter view: six learning nodes (FEN + prompt + hint count,
 *   NO solution — plan A7) + which the owner has completed + chapter status.
 *
 * POST /api/gamification/companion/watchtower
 *   body: { node: 'W01'..'W06', submission: { uci? | squares? } }
 *   Server judges the node (chess.js / set match), records the attempt, and when
 *   ALL six nodes have a correct attempt grants the chapter_first reward exactly
 *   once via companion:chapter:<owner>:watchtower. The response NEVER contains the
 *   solution. Completion is computed server-side (not a client flag).
 *
 * Behind both companion flags; unlinked callers get 403. Never coin-gated (R1).
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { COMPANION_ENABLED } from '@/lib/feature-flags';
import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg } from '@/lib/companion/service';
import { loadWatchtower, recordLearningNode } from '@/lib/companion/watchtower-service';

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

  const view = await loadWatchtower(r.ownerUserId);
  return NextResponse.json(view, { status: 200 });
}

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
  const node = typeof body?.node === 'string' ? body.node : null;
  const submission =
    body?.submission && typeof body.submission === 'object' ? body.submission : null;
  if (!node || !submission) {
    return NextResponse.json({ error: 'node and submission required' }, { status: 400 });
  }

  const result = await recordLearningNode({
    ownerUserId: r.ownerUserId,
    orgId: r.orgId,
    studentId: r.studentId,
    node,
    submission,
  });

  if (result.status === 'not_found') {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }
  return NextResponse.json(result, { status: 200 });
}
