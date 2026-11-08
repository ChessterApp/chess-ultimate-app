/**
 * GET /api/chess-empire/register/options
 *
 * Public JSON twin of the `/register` branch picker for the mobile app. Same
 * data as the page (`loadRegisterOptions`, lib/register-options.ts): the org's
 * active branch-invite tokens deduped to the newest per branch, plus the newest
 * online-kind token. No auth — the page is public and already renders every
 * token as a `/welcome/<token>` link. No org on the host (apex) → the empty
 * state, exactly as the page does.
 */
import 'server-only';
import { NextResponse } from 'next/server';
import { headers } from 'next/headers';
import { loadRegisterOptions } from '@/lib/register-options';

export const dynamic = 'force-dynamic';

export async function GET() {
  const headersList = await headers();
  const orgId = headersList.get('x-org-id');
  const options = orgId
    ? await loadRegisterOptions(orgId)
    : { branches: [], online: null };
  return NextResponse.json(options);
}
