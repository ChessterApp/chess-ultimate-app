/**
 * POST /api/chess-empire/sync/freeze-thaw
 *
 * Event-driven single-student freeze/thaw. The Chess Empire admin app POSTs
 * here (fire-and-forget) the instant an admin flips a student's status between
 * `active` and `frozen`, so the change applies immediately instead of waiting
 * for the hourly reconcile cron (scripts/sync-chess-empire-members.mjs), which
 * stays as the safety net.
 *
 * Auth: a shared service token in `CE_SYNC_SERVICE_TOKEN`, sent as
 * `Authorization: Bearer <token>` (or `X-CE-Sync-Token`). Fails closed if the
 * env var is unset. The actual freeze/thaw + Clerk-membership logic lives in
 * `syncFreezeThawByStudent` (@/lib/chess-empire-admin) and mirrors the cron.
 *
 * Body: `{ external_student_id: string, status: 'active' | 'frozen' }`.
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { timingSafeEqual } from 'node:crypto';
import { clerkClient } from '@clerk/nextjs/server';
import {
  syncFreezeThawByStudent,
  NotFoundError,
  type CeSyncClerkAdapter,
} from '@/lib/chess-empire-admin';

export const dynamic = 'force-dynamic';

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'authorization, content-type, x-ce-sync-token',
};

function corsJson(body: unknown, status: number): NextResponse {
  return NextResponse.json(body, {
    status,
    headers: { 'Access-Control-Allow-Origin': '*' },
  });
}

export function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: CORS_HEADERS });
}

/** Constant-time token compare (length-guarded so timingSafeEqual never throws). */
function tokenMatches(provided: string, expected: string): boolean {
  const a = Buffer.from(provided);
  const b = Buffer.from(expected);
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

function authorized(req: NextRequest): boolean {
  const expected = process.env.CE_SYNC_SERVICE_TOKEN;
  if (!expected) return false; // fail closed when unconfigured
  const bearer = req.headers.get('authorization')?.replace(/^Bearer\s+/i, '').trim();
  const header = req.headers.get('x-ce-sync-token')?.trim();
  const provided = bearer || header;
  if (!provided) return false;
  return tokenMatches(provided, expected);
}

/** Clerk already-a-member (422) — treat as success on create. */
function isAlreadyMemberError(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false;
  const e = err as { status?: number; errors?: Array<{ code?: string }> };
  if (e.status === 422) return true;
  return Array.isArray(e.errors)
    && e.errors[0]?.code === 'already_a_member_of_organization';
}

/** Clerk membership already gone (404) — treat as success on delete. */
function isNotFoundError(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false;
  return (err as { status?: number }).status === 404;
}

/** Real Clerk adapter, idempotent like the cron's REST client. */
function realClerkAdapter(): CeSyncClerkAdapter {
  return {
    async createMembership(clerkOrgId, userId) {
      try {
        const client = await clerkClient();
        await client.organizations.createOrganizationMembership({
          organizationId: clerkOrgId,
          userId,
          role: 'org:member',
        });
      } catch (err) {
        if (isAlreadyMemberError(err)) return;
        throw err;
      }
    },
    async deleteMembership(clerkOrgId, userId) {
      try {
        const client = await clerkClient();
        await client.organizations.deleteOrganizationMembership({
          organizationId: clerkOrgId,
          userId,
        });
      } catch (err) {
        if (isNotFoundError(err)) return;
        throw err;
      }
    },
  };
}

export async function POST(req: NextRequest) {
  if (!authorized(req)) {
    return corsJson({ error: 'Unauthorized' }, 401);
  }

  let body: { external_student_id?: unknown; status?: unknown };
  try {
    body = (await req.json()) as typeof body;
  } catch {
    return corsJson({ error: 'invalid_json' }, 400);
  }

  const externalStudentId =
    typeof body.external_student_id === 'string' ? body.external_student_id.trim() : '';
  const status = body.status;
  if (!externalStudentId || (status !== 'active' && status !== 'frozen')) {
    return corsJson({ error: 'invalid_request' }, 400);
  }

  try {
    const result = await syncFreezeThawByStudent({
      externalStudentId,
      ceStatus: status,
      clerk: realClerkAdapter(),
    });
    return corsJson({ ok: true, ...result }, 200);
  } catch (err) {
    if (err instanceof NotFoundError) {
      return corsJson({ error: 'student_not_found' }, 404);
    }
    console.error('[ce-sync/freeze-thaw] failed', err);
    return corsJson({ error: 'internal_error' }, 500);
  }
}
