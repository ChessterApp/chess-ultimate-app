/**
 * POST /api/gamification/companion/egg   body: { species }
 *
 * The "choose your egg" onboarding step: persists the chosen egg variant on the
 * caller's companion row (species), keeping it in the `egg` stage. Idempotent —
 * re-choosing overwrites the species, never double-creates. Behind the same two
 * flags as the GET route (either off ⇒ 404). No coins involved (R1).
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { COMPANION_ENABLED } from '@/lib/feature-flags';
import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg, chooseEgg } from '@/lib/companion/service';

export const dynamic = 'force-dynamic';

const STATUS_HTTP: Record<string, number> = {
  ok: 200,
  invalid_species: 400,
  already_hatched: 409,
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
  const species = typeof body?.species === 'string' ? body.species : null;
  if (!species) {
    return NextResponse.json({ error: 'species required' }, { status: 400 });
  }

  const result = await chooseEgg(r.ownerUserId, species);
  const http = STATUS_HTTP[result.status] ?? 400;
  return NextResponse.json(result, { status: http });
}
