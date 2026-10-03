/**
 * POST /api/gamification/companion/hatch   body: { name }
 *
 * The hatch moment: commits the companion (egg → hatched), the one-time starter
 * accessory entitlement, and the hatch reward in ONE idempotent RPC
 * (`hatch_companion`), then returns the canonical result so the client can play
 * the reveal. Readiness is re-verified server-side from authoritative evidence —
 * a client "ready" flag is never trusted (spec §12.4). Double-submitting hatches
 * exactly once (already_hatched, same companion). Behind BOTH companion flags
 * (either off ⇒ 404); unlinked callers get 403. Hatching is a reward, never
 * coin-gated (R1). Mirrors shop/buy + the Phase 2 companion routes.
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { COMPANION_ENABLED } from '@/lib/feature-flags';
import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg, hatchCompanion } from '@/lib/companion/service';
import { sanitizeCompanionName } from '@/lib/companion/state';

export const dynamic = 'force-dynamic';

const STATUS_HTTP: Record<string, number> = {
  ok: 200,
  already_hatched: 200, // idempotent
  not_ready: 409,
};

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
  const name = sanitizeCompanionName(body?.name);
  if (!name) {
    return NextResponse.json({ error: 'invalid_name' }, { status: 400 });
  }

  const result = await hatchCompanion({
    ownerUserId: r.ownerUserId,
    orgId: r.orgId,
    studentId: r.studentId,
    name,
  });
  const http = STATUS_HTTP[result.status] ?? 400;
  return NextResponse.json(result, { status: http });
}
