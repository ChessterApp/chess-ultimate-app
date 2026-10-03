/**
 * GET /api/gamification/companion
 *
 * The companion view for the caller's linked CE student: their companion row
 * (null until an egg is chosen), the competency ring, and the hatch gate. Behind
 * BOTH the UI kill-switch (`COMPANION_ENABLED` env) and the per-org server flag
 * (`companions_enabled` in gamification_settings) — either off ⇒ 404, so the
 * feature stays fully dark (hard constraint, plan A6). Unlinked callers get 403
 * (D-8) and nothing accrues; reading progress is never coin-gated (R1).
 */
import 'server-only';
import { NextResponse } from 'next/server';
import { COMPANION_ENABLED } from '@/lib/feature-flags';
import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg, loadCompanionView } from '@/lib/companion/service';

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

  const view = await loadCompanionView(r.ownerUserId);
  return NextResponse.json(view);
}
