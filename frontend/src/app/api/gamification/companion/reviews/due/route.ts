/**
 * GET /api/gamification/companion/reviews/due
 *
 * The pull-based SM-2 due queue (plan A4): competencies whose next_review_at is
 * due (<= now) or null, scoped to the resolved owner. Returns review items with
 * NO solution fields. Behind both companion flags (UI kill-switch + per-org
 * server flag); unlinked callers get 403. Reviewing is never coin-gated (R1).
 */
import 'server-only';
import { NextResponse } from 'next/server';
import { COMPANION_ENABLED } from '@/lib/feature-flags';
import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg } from '@/lib/companion/service';
import { loadDueReviews } from '@/lib/companion/review-service';

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

  const due = await loadDueReviews(r.ownerUserId);
  return NextResponse.json({ due, count: due.length }, { status: 200 });
}
