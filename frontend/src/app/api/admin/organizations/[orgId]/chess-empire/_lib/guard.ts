/**
 * Shared admin guard for the Chess Empire admin routes.
 *
 * Mirrors the pattern from `members/route.ts`: verify Clerk session, then
 * delegate to the Flask backend for the actual org-membership/role check.
 * The Flask `_require_admin` is the single source of truth for "is this
 * user an admin of this org" — see `backend/routes/admin.py`.
 */
import 'server-only';
import { NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5001';

export type AdminGuardResult =
  | { ok: true; userId: string }
  | { ok: false; response: NextResponse };

interface BackendMembersResponse {
  members?: Array<{ user_id?: string; role?: string }>;
}

export async function requireOrgAdmin(orgId: string): Promise<AdminGuardResult> {
  const { userId } = await auth();
  if (!userId) {
    return {
      ok: false,
      response: NextResponse.json({ error: 'Unauthorized' }, { status: 401 }),
    };
  }
  if (!orgId) {
    return {
      ok: false,
      response: NextResponse.json({ error: 'missing_org' }, { status: 400 }),
    };
  }
  try {
    const res = await fetch(
      `${BACKEND_URL}/api/admin/organizations/${orgId}/members?user_id=${encodeURIComponent(
        userId,
      )}`,
      {
        headers: { 'X-User-Id': userId },
        signal: AbortSignal.timeout(10_000),
      },
    );
    if (res.status === 401 || res.status === 403) {
      return {
        ok: false,
        response: NextResponse.json({ error: 'Forbidden' }, { status: 403 }),
      };
    }
    if (!res.ok) {
      return {
        ok: false,
        response: NextResponse.json(
          { error: 'backend_error' },
          { status: 502 },
        ),
      };
    }
    const data = (await res.json().catch(() => ({}))) as BackendMembersResponse;
    const me = (data.members ?? []).find((m) => m.user_id === userId);
    const role = me?.role ?? '';
    if (role !== 'admin' && role !== 'owner') {
      return {
        ok: false,
        response: NextResponse.json({ error: 'Forbidden' }, { status: 403 }),
      };
    }
    return { ok: true, userId };
  } catch {
    return {
      ok: false,
      response: NextResponse.json(
        { error: 'Service unavailable' },
        { status: 502 },
      ),
    };
  }
}
