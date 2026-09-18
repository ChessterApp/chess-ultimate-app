/**
 * POST /api/chess-empire/tournaments/[id]/register  — register a family member
 * DELETE /api/chess-empire/tournaments/[id]/register — cancel a family member
 *
 * Both require a Clerk session AND at least one VERIFIED Chess Empire link. A
 * Chesster account may hold several verified student links ("family members");
 * the caller may act on ANY of their OWN verified students and NEVER anyone
 * else's. The `student_id` in the request is honoured only if it appears in the
 * caller's verified allowlist (`getVerifiedMembersForUser`) — an unrecognised id
 * is rejected 403 `forbidden_student` and never forwarded to Chess Empire. When
 * no `student_id` is given: a single-link account uses its one student; a
 * multi-link account must specify which (400 `student_required`).
 *
 * The service key stays server-side; CE errors are mapped to clean JSON
 * `{ error, message }`.
 */
import 'server-only';
import { NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { getVerifiedMembersForUser } from '@/lib/chess-empire-member';
import { getFamilyLinkedStudentIds } from '@/lib/family-link-invite';
import {
  registerForTournament,
  cancelTournamentRegistration,
  getStudentTournamentRegistrations,
  ChessEmpireAPIError,
} from '@/lib/chess-empire-client';

interface RouteContext {
  params: Promise<{ id: string }>;
}

/** Pull the RPC failure reason out of a ChessEmpireAPIError body. */
function extractReason(body: unknown): string {
  if (body && typeof body === 'object' && 'reason' in body) {
    const reason = (body as { reason?: unknown }).reason;
    if (typeof reason === 'string') return reason;
  }
  return 'server_error';
}

/** Map a CE reason code → client-facing code + copy + HTTP status. */
function mapRegisterError(reason: string): {
  code: string;
  message: string;
  status: number;
} {
  switch (reason) {
    case 'full':
      return { code: 'full', message: 'This tournament is full.', status: 409 };
    case 'closed':
      return {
        code: 'closed',
        message: 'Registration has closed for this tournament.',
        status: 409,
      };
    case 'duplicate':
      return {
        code: 'duplicate',
        message: "You're already registered for this tournament.",
        status: 409,
      };
    case 'ineligible':
      return {
        code: 'ineligible',
        message: 'You are not eligible for this tournament.',
        status: 409,
      };
    case 'no_razryad':
      return {
        code: 'no_razryad',
        message:
          'Registration is only available to students with a razryad (chess rating category).',
        status: 409,
      };
    case 'not_found':
      return { code: 'not_found', message: 'Tournament not found.', status: 404 };
    case 'invalid_input':
      return {
        code: 'invalid_input',
        message: 'Invalid registration request.',
        status: 400,
      };
    default:
      return {
        code: 'server_error',
        message: 'Registration failed. Please try again.',
        status: 502,
      };
  }
}

/**
 * Read an optional `student_id` from the request: JSON body (POST + DELETE) or
 * `?student_id=` query param (DELETE). Tolerates an empty/absent/malformed body
 * — the current frontend sends none. Returns a trimmed id or null.
 */
async function readRequestedStudentId(req: Request): Promise<string | null> {
  const fromQuery = new URL(req.url).searchParams.get('student_id');
  if (fromQuery && fromQuery.trim()) return fromQuery.trim();
  let raw = '';
  try {
    raw = await req.text();
  } catch {
    return null;
  }
  if (!raw.trim()) return null;
  try {
    const parsed = JSON.parse(raw) as { student_id?: unknown };
    const sid = parsed?.student_id;
    return typeof sid === 'string' && sid.trim() ? sid.trim() : null;
  } catch {
    return null;
  }
}

/**
 * Resolve the target student from the caller's verified allowlist, or a
 * NextResponse to short-circuit. Enforces the family invariant: the returned id
 * is ALWAYS one of the caller's own verified students.
 */
async function resolveTargetStudent(
  req: Request,
): Promise<{ studentId: string } | NextResponse> {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json(
      { error: 'unauthorized', message: 'Sign in to register.' },
      { status: 401 },
    );
  }
  let members;
  try {
    members = await getVerifiedMembersForUser(userId);
  } catch (err) {
    console.error('[chess-empire/tournaments/register] member lookup failed', err);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }
  // Owned links PLUS students reached through accepted cross-branch family
  // invites — "any family member can register any other". The family-edge lookup
  // is best-effort (returns [] on failure) so it never blocks an owned student.
  const familyLinked = await getFamilyLinkedStudentIds(userId);
  const allowed = Array.from(
    new Set(
      [
        ...members.map((m) => m.studentId),
        ...familyLinked.map((f) => f.studentId),
      ].filter((id): id is string => !!id),
    ),
  );
  if (allowed.length === 0) {
    return NextResponse.json(
      {
        error: 'forbidden',
        message: 'Only verified Chess Empire members can register.',
      },
      { status: 403 },
    );
  }

  const requested = await readRequestedStudentId(req);
  if (requested) {
    // NEVER forward an id the caller doesn't own to Chess Empire.
    if (!allowed.includes(requested)) {
      return NextResponse.json({ error: 'forbidden_student' }, { status: 403 });
    }
    return { studentId: requested };
  }
  if (allowed.length === 1) return { studentId: allowed[0] };
  return NextResponse.json(
    {
      error: 'student_required',
      message: 'Specify which family member to register.',
    },
    { status: 400 },
  );
}

export async function POST(req: Request, ctx: RouteContext) {
  const { id } = await ctx.params;
  const resolved = await resolveTargetStudent(req);
  if (resolved instanceof NextResponse) return resolved;

  try {
    const result = await registerForTournament(id, resolved.studentId, 'web');
    return NextResponse.json({ ...result, ok: true });
  } catch (err) {
    if (err instanceof ChessEmpireAPIError) {
      const mapped = mapRegisterError(extractReason(err.body));
      return NextResponse.json(
        { error: mapped.code, message: mapped.message },
        { status: mapped.status },
      );
    }
    console.error('[chess-empire/tournaments/register] failed', err);
    return NextResponse.json(
      { error: 'server_error', message: 'Registration failed. Please try again.' },
      { status: 502 },
    );
  }
}

export async function DELETE(req: Request, ctx: RouteContext) {
  const { id } = await ctx.params;
  const resolved = await resolveTargetStudent(req);
  if (resolved instanceof NextResponse) return resolved;

  try {
    const regs = await getStudentTournamentRegistrations(resolved.studentId);
    const registration = regs.find((r) => r.tournament_id === id);
    if (!registration) {
      return NextResponse.json(
        { error: 'not_found', message: 'No registration found to cancel.' },
        { status: 404 },
      );
    }
    await cancelTournamentRegistration(registration.id);
    return NextResponse.json({ ok: true });
  } catch (err) {
    if (err instanceof ChessEmpireAPIError) {
      const mapped = mapRegisterError(extractReason(err.body));
      return NextResponse.json(
        { error: mapped.code, message: mapped.message },
        { status: mapped.status },
      );
    }
    console.error('[chess-empire/tournaments/register] cancel failed', err);
    return NextResponse.json(
      { error: 'server_error', message: 'Could not cancel. Please try again.' },
      { status: 502 },
    );
  }
}
