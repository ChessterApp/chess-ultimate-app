/**
 * POST /api/admin/organizations/[orgId]/chess-empire/link
 *
 * Org-admin-gated manual link endpoint. Body: `{userId, studentId, notes?, source?}`.
 * Idempotent — the underlying `adminLinkStudent` upserts on the
 * (org, external_student_id, chess_empire) unique constraint. Also used by
 * the Vasco-style backfill (source='backfill').
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { requireOrgAdmin } from '../_lib/guard';
import {
  adminLinkStudent,
  logAdminLinkAttempt,
} from '@/lib/chess-empire-admin';

interface Body {
  userId?: string;
  studentId?: string;
  notes?: string | null;
  source?: 'admin_manual' | 'backfill';
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ orgId: string }> },
) {
  const { orgId } = await params;
  const guard = await requireOrgAdmin(orgId);
  if (!guard.ok) return guard.response;

  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ error: 'bad_json' }, { status: 400 });
  }
  const userId = body.userId?.trim();
  const studentId = body.studentId?.trim();
  const source = body.source === 'backfill' ? 'backfill' : 'admin_manual';
  const notes = typeof body.notes === 'string' ? body.notes.trim() || null : null;
  if (!userId || !studentId) {
    return NextResponse.json(
      { error: 'missing_userId_or_studentId' },
      { status: 400 },
    );
  }

  try {
    const member = await adminLinkStudent({
      orgId,
      targetUserId: userId,
      studentId,
      actorClerkUserId: guard.userId,
      notes,
      source,
    });
    await logAdminLinkAttempt({
      orgId,
      targetUserId: userId,
      studentId,
      status: 'success',
      source,
    });
    return NextResponse.json({ ok: true, member });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    await logAdminLinkAttempt({
      orgId,
      targetUserId: userId,
      studentId,
      status: 'webhook_error',
      errorMessage: message,
      source,
    }).catch(() => {});
    console.error('[admin/link] failed', err);
    if (/already linked to a different student/.test(message)) {
      return NextResponse.json(
        { error: 'user_already_linked' },
        { status: 409 },
      );
    }
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }
}
