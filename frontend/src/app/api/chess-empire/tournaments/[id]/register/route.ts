/**
 * POST /api/chess-empire/tournaments/[id]/register  — self-register
 * DELETE /api/chess-empire/tournaments/[id]/register — self-cancel
 *
 * Both require a Clerk session AND a verified Chess Empire membership. The
 * student id is ALWAYS resolved from the verified member — a `student_id` in the
 * request body is never read, so a caller cannot register anyone but themself.
 * The service key stays server-side; CE errors are mapped to clean JSON
 * `{ error, message }`.
 */
import 'server-only';
import { NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { getMembershipStateForUser } from '@/lib/chess-empire-member';
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

/** Resolve the caller's verified member, or a NextResponse to short-circuit. */
async function requireVerifiedMember(): Promise<
  { studentId: string } | NextResponse
> {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json(
      { error: 'unauthorized', message: 'Sign in to register.' },
      { status: 401 },
    );
  }
  let member;
  try {
    member = await getMembershipStateForUser(userId);
  } catch (err) {
    console.error('[chess-empire/tournaments/register] member lookup failed', err);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }
  if (member.state !== 'verified' || !member.studentId) {
    return NextResponse.json(
      {
        error: 'forbidden',
        message: 'Only verified Chess Empire members can register.',
      },
      { status: 403 },
    );
  }
  return { studentId: member.studentId };
}

export async function POST(_req: Request, ctx: RouteContext) {
  const { id } = await ctx.params;
  const resolved = await requireVerifiedMember();
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

export async function DELETE(_req: Request, ctx: RouteContext) {
  const { id } = await ctx.params;
  const resolved = await requireVerifiedMember();
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
