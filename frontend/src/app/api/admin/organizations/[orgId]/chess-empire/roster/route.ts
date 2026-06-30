/**
 * GET /api/admin/organizations/[orgId]/chess-empire/roster
 *
 * Single round-trip the ChessEmpirePanel uses to render the page: returns
 * Chesster-side CE-linked members + CE-side branches/coaches/active
 * students. Each CE call degrades to `[]` on failure — the panel must still
 * render even if part of CE is down.
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { requireOrgAdmin } from '../_lib/guard';
import { listOrgCeMembers } from '@/lib/chess-empire-admin';
import {
  listBranches,
  listCoaches,
  listActiveStudentsByBranch,
  type CEActiveStudent,
} from '@/lib/chess-empire-client';

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ orgId: string }> },
) {
  const { orgId } = await params;
  const guard = await requireOrgAdmin(orgId);
  if (!guard.ok) return guard.response;

  const [ceMembers, branches, coaches] = await Promise.all([
    listOrgCeMembers(orgId).catch(() => []),
    listBranches().catch(() => []),
    listCoaches().catch(() => []),
  ]);

  const studentLists = await Promise.all(
    branches.map((b) =>
      listActiveStudentsByBranch(b.id).catch(() => [] as CEActiveStudent[]),
    ),
  );
  const ceActiveStudents = studentLists.flat();

  return NextResponse.json({
    ceMembers,
    ceActiveStudents,
    branches,
    coaches,
  });
}
