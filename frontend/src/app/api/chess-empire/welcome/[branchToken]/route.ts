/**
 * GET /api/chess-empire/welcome/[branchToken]
 *
 * Public JSON twin of the `/welcome/<branchToken>` page header for the mobile
 * app: the branch name for the greeting and the token kind (`online` shows the
 * CE Online copy and the 3-day trial CTA). Same resolver as the page
 * (`resolveWelcomeToken`, lib/branch-invite-token.ts).
 *
 * No auth — the page is public. Rate-limited 30 req/min per IP like the
 * sibling `students/search` endpoint. A missing, revoked or expired token →
 * 404 `invalid_token` (the page's "link no longer valid" screen). Only
 * `{ branchName, kind }` is returned — never the org or external branch id.
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { resolveWelcomeToken } from '@/lib/branch-invite-token';
import { rateLimit } from '@/lib/in-memory-rate-limit';

export const dynamic = 'force-dynamic';

const WELCOME_RATE_LIMIT = 30;
const WELCOME_WINDOW_MS = 60_000;

function clientIp(req: NextRequest): string {
  const forwarded = req.headers.get('x-forwarded-for');
  if (forwarded) return forwarded.split(',')[0]!.trim();
  return req.headers.get('x-real-ip') ?? 'unknown';
}

export async function GET(
  req: NextRequest,
  ctx: { params: Promise<{ branchToken: string }> },
) {
  const ip = clientIp(req);
  const limit = rateLimit(`ce-welcome:${ip}`, WELCOME_RATE_LIMIT, WELCOME_WINDOW_MS);
  if (!limit.allowed) {
    return NextResponse.json(
      { error: 'rate_limited' },
      { status: 429, headers: { 'Retry-After': String(limit.retryAfterSeconds) } },
    );
  }

  const { branchToken } = await ctx.params;
  const resolved = await resolveWelcomeToken(branchToken);
  if (!resolved) {
    return NextResponse.json({ error: 'invalid_token' }, { status: 404 });
  }
  return NextResponse.json({ branchName: resolved.branchName, kind: resolved.kind });
}
