import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { logLiveGameEvent } from '@/lib/live-game/log';

// Online play (Stage A) — client telemetry sink.
//
// The client fires fire-and-forget POSTs here on realtime lifecycle events
// (channel status changes, presence join/leave, token refresh, resubscribe,
// poll fallback, disconnect banner) so the "opponent disconnected / frozen
// board" failure mode is diagnosable from the server. Writes land in
// `live_game_logs` with source='client'.
//
// Lightweight validation: Clerk-authed + the action must be on a fixed
// whitelist. We do NOT do a per-event player lookup (that would add a DB round
// trip to every ping); the row records the authed user + game id for context.

const ALLOWED_ACTIONS = new Set([
  'channel_status',
  'presence_join',
  'presence_leave',
  'token_refresh',
  'resubscribe',
  'poll_fallback_hydrate',
  'disconnect_shown',
]);

/** Hard cap on the serialized detail payload to keep log rows bounded. */
const MAX_DETAIL_BYTES = 1024;

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ gameId: string }> },
) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }
  const { gameId } = await params;

  let body: { action?: unknown; ply?: unknown; detail?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'bad_json' }, { status: 400 });
  }

  const action = typeof body.action === 'string' ? body.action : '';
  if (!ALLOWED_ACTIONS.has(action)) {
    return NextResponse.json({ error: 'bad_action' }, { status: 400 });
  }

  const ply =
    typeof body.ply === 'number' && Number.isInteger(body.ply) ? body.ply : null;

  // Cap the detail payload — drop it entirely if oversized rather than reject.
  let detail: Record<string, unknown> | null = null;
  if (body.detail && typeof body.detail === 'object') {
    try {
      const serialized = JSON.stringify(body.detail);
      if (serialized.length <= MAX_DETAIL_BYTES) {
        detail = body.detail as Record<string, unknown>;
      } else {
        detail = { _truncated: true };
      }
    } catch {
      detail = null;
    }
  }

  logLiveGameEvent({
    source: 'client',
    action,
    gameId,
    userId,
    ply,
    detail,
  });

  return NextResponse.json({ ok: true }, { status: 202 });
}
