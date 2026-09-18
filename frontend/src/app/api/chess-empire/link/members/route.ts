/**
 * GET /api/chess-empire/link/members
 *
 * The caller's family allowlist — every VERIFIED Chess Empire link the signed-in
 * Clerk user owns, with each member's display name, relationship tag
 * (self/child/other) and link status. Backs the Family card on the profile page
 * (a client component that can't call the server-only membership lib directly).
 *
 * Also returns `branchToken`: a currently-valid branch invite token resolved
 * server-side from the primary verified member (student → CE branch → active
 * `branch_invite_tokens` row). This lets the "add family member" panel scope its
 * student search on any signed-in device, not just the one that stashed the
 * branch-welcome URL during onboarding. `null` when no active token is found.
 *
 * Never reveals other users' links — every row is scoped to the caller's own
 * Clerk user id by the underlying membership lib.
 */
import 'server-only';
import { NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { getVerifiedMembersForUser } from '@/lib/chess-empire-member';
import {
  getStudentDisplayName,
  getStudentBranches,
} from '@/lib/chess-empire-client';
import { supabaseAdmin } from '@/lib/supabase-admin';

interface BranchTokenRow {
  token: string;
  kind: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string | null;
}

/**
 * Resolve a currently-valid, non-online branch invite token for the branch the
 * given student belongs to. Best-effort: returns null on any failure so the
 * add-member panel simply falls back to its "open your invite link" copy.
 */
async function resolveBranchTokenForStudent(
  studentId: string,
): Promise<string | null> {
  try {
    const branches = await getStudentBranches([studentId]);
    const branchId = branches.get(studentId) ?? null;
    if (!branchId) return null;

    const { data, error } = await supabaseAdmin
      .from('branch_invite_tokens')
      .select('token, kind, expires_at, revoked_at, created_at')
      .eq('external_branch_id', branchId);
    if (error || !data) return null;

    const now = Date.now();
    const active = (data as BranchTokenRow[]).filter((row) => {
      if (row.revoked_at) return false;
      if (row.kind === 'online') return false;
      if (row.expires_at && new Date(row.expires_at).getTime() < now) return false;
      return true;
    });
    // Newest token per branch wins — mirrors the /register picker.
    active.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
    return active[0]?.token ?? null;
  } catch {
    return null;
  }
}

export async function GET() {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const members = await getVerifiedMembersForUser(userId);
    const withNames = await Promise.all(
      members.map(async (m) => ({
        studentId: m.studentId as string,
        name: m.studentId
          ? await getStudentDisplayName(m.studentId).catch(() => null)
          : null,
        relationship: m.relationship,
        status: m.state,
      })),
    );

    // Server-side branch resolution for the cross-device add-member flow: derive
    // the branch from the primary verified member ('self' wins, else the first).
    const primary = members.find((m) => m.relationship === 'self') ?? members[0];
    const branchToken = primary?.studentId
      ? await resolveBranchTokenForStudent(primary.studentId)
      : null;

    return NextResponse.json({ members: withNames, branchToken });
  } catch (err) {
    console.error('[chess-empire/link/members] lookup failed', err);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }
}
