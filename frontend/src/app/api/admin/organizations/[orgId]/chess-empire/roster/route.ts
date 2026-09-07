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

  // Each source still degrades to [] so the panel renders, but a failure now
  // records a warning surfaced in the response — a silent-empty roster hid a
  // 2-month CE outage. `warnings` is empty on full success.
  const warnings: string[] = [];
  function degrade<T>(source: string, fallback: T) {
    return (err: unknown): T => {
      const message = err instanceof Error ? err.message : String(err);
      console.error(`[ce-roster] ${source} failed:`, message);
      warnings.push(`${source}: ${message}`);
      return fallback;
    };
  }

  const [ceMembers, branches, coaches] = await Promise.all([
    listOrgCeMembers(orgId).catch(degrade('members', [])),
    listBranches().catch(degrade('branches', [])),
    listCoaches().catch(degrade('coaches', [])),
  ]);

  const studentLists = await Promise.all(
    branches.map((b) =>
      listActiveStudentsByBranch(b.id).catch(
        degrade(`students(${b.id})`, [] as CEActiveStudent[]),
      ),
    ),
  );
  const ceActiveStudents = studentLists.flat();

  return NextResponse.json({
    ceMembers,
    ceActiveStudents,
    branches,
    coaches,
    warnings,
  });
}
