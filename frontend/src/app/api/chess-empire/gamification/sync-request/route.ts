/**
 * POST /api/chess-empire/gamification/sync-request
 *
 * Browser-callable sibling of `sync/route.ts`. The Chess Empire admin app
 * (vanilla JS on another origin, e.g. https://admin.chessempire.kz) POSTs here
 * right after each tournament table upload so XP/coins land immediately instead
 * of waiting for the cron.
 *
 * The admin cannot hold CRON_SECRET (client-side code), so auth is the admin's
 * Chess Empire Supabase *user* access token, verified server-side against the
 * CE project via `auth.getUser`. Missing header/env or an invalid token → 401
 * (fail closed). On success it does exactly what `sync/route.ts` does: loop
 * `syncOrg` over every org with a gamification_settings row.
 *
 * A best-effort module-level cooldown/in-flight guard skips runs that would
 * fire within 60s of the last one (or while one is in flight) → HTTP 202.
 * Serverless instances don't share memory, so this is hygiene, not correctness
 * — syncOrg is idempotent.
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { type OrgSyncSummary, syncOrg } from '@/lib/gamification/sync-run';

export const dynamic = 'force-dynamic';

const COOLDOWN_MS = 60_000;

// Module-level, best-effort guard. Not shared across serverless instances.
let inFlight = false;
let lastRunAt = 0;

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'authorization, content-type',
};

/** JSON response with the CORS header the browser caller needs. */
function corsJson(body: unknown, status: number): NextResponse {
  return NextResponse.json(body, {
    status,
    headers: { 'Access-Control-Allow-Origin': '*' },
  });
}

/**
 * Verify the bearer token as a Chess Empire Supabase user access token. Returns
 * true only for a valid, resolvable user. Fails closed on a missing header,
 * missing env, or any verification error.
 */
async function verifyCeToken(req: NextRequest): Promise<boolean> {
  const token = req.headers.get('authorization')?.replace(/^Bearer\s+/i, '').trim();
  if (!token) return false;

  const url = process.env.CHESS_EMPIRE_SUPABASE_URL;
  const key = process.env.CHESS_EMPIRE_SERVICE_KEY;
  if (!url || !key) return false;

  try {
    const client = createClient(url, key);
    const { data, error } = await client.auth.getUser(token);
    return !error && !!data?.user;
  } catch {
    return false;
  }
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: CORS_HEADERS });
}

export async function POST(req: NextRequest) {
  if (!(await verifyCeToken(req))) {
    return corsJson({ error: 'Unauthorized' }, 401);
  }

  if (inFlight || Date.now() - lastRunAt < COOLDOWN_MS) {
    return corsJson({ ok: true, skipped: 'cooldown' }, 202);
  }

  inFlight = true;
  try {
    const { data: orgs } = await supabaseAdmin
      .from('gamification_settings')
      .select('organization_id');

    const results: OrgSyncSummary[] = [];
    for (const o of orgs ?? []) {
      results.push(await syncOrg(o.organization_id as string));
    }

    return corsJson(
      { ok: true, ran_at: new Date().toISOString(), orgs: results },
      200,
    );
  } finally {
    lastRunAt = Date.now();
    inFlight = false;
  }
}
