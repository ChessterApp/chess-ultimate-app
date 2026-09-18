/**
 * DELETE /api/chess-empire/link/members/[studentId]
 *
 * Unlink a family member from the caller's account. Hard-deletes the caller's
 * OWN `organization_members` row for the given external student id. Re-linking
 * later goes back through the normal search → verify → claim flow.
 *
 * Guards:
 *  - Caller must be authenticated (401).
 *  - The target row must belong to the caller's OWN Clerk user — the lookup is
 *    scoped by `user_id`, so a row that isn't theirs is simply "not found"
 *    (404); we never reveal another user's links.
 *  - Only `relationship IN ('child','other')` may be removed. Removing the
 *    `self` link ("delete my Chess Empire identity") is out of scope → 403.
 *
 * No Chess Empire-side calls: the student keeps existing in Chess Empire and any
 * existing tournament registrations at the school are untouched. Idempotent in
 * effect — a repeat delete of an already-removed row finds nothing and 404s with
 * no side effects.
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { supabaseAdmin } from '@/lib/supabase-admin';

const MEMBER_SOURCES = ['chess_empire', 'online'];

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ studentId: string }> },
) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { studentId } = await params;
  const id = studentId?.trim();
  if (!id) {
    return NextResponse.json({ error: 'missing_student' }, { status: 400 });
  }

  // Scope strictly to the caller's own rows — a foreign or absent row is 404.
  const { data, error } = await supabaseAdmin
    .from('organization_members')
    .select('id, relationship')
    .eq('user_id', userId)
    .eq('external_student_id', id)
    .in('external_source', MEMBER_SOURCES)
    .maybeSingle();
  if (error) {
    console.error('[chess-empire/link/members DELETE] lookup failed', error);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }
  if (!data) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }

  const row = data as { id: string; relationship: string | null };
  // Pre-migration rows (null relationship) read as 'self'.
  const relationship = row.relationship ?? 'self';
  if (relationship !== 'child' && relationship !== 'other') {
    return NextResponse.json({ error: 'cannot_remove_self' }, { status: 403 });
  }

  const { error: deleteError } = await supabaseAdmin
    .from('organization_members')
    .delete()
    .eq('id', row.id)
    .eq('user_id', userId);
  if (deleteError) {
    console.error('[chess-empire/link/members DELETE] delete failed', deleteError);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }

  return NextResponse.json({ ok: true });
}
