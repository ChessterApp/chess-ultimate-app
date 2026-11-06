/**
 * GET /api/chess-empire/learn/floor
 *
 * The Chess Empire Learn level floor for the caller, as JSON — the value the
 * `/learn` page passes to `LearnClient` as `ceLevelFloor`. Reuses
 * `resolveCeLevelFloor` verbatim: it reads the tenant headers and the Clerk
 * session itself and never throws. Signed-out callers, other hosts, online
 * members, coaches, and any lookup failure all get `{ floor: null }`, exactly
 * as the page renders them (plain progressive unlock).
 */
import 'server-only';
import { NextResponse } from 'next/server';
import { resolveCeLevelFloor } from '@/lib/learn-ce-floor';

export const dynamic = 'force-dynamic';

export async function GET() {
  const floor = await resolveCeLevelFloor();
  return NextResponse.json({ floor: floor ?? null });
}
