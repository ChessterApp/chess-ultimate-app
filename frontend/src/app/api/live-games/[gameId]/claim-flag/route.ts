import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { broadcastGameEvent } from '@/lib/live-game/broadcast';
import { remainingMs } from '@/lib/live-game/clocks';
import { turnFromFen } from '@/lib/live-game/validate';
import type { GameRow } from '@/lib/live-game/types';

// Online play (phase 4) — claim a flag (win/loss on time).
//
// The client is never trusted: we re-derive the live clocks from the stored
// banks + server time. Only the side-to-move's clock is running, so the flag
// rule is simply "whoever is on the move with a spent bank loses". This makes
// both cases the spec calls out fall out for free:
//   * claimant is the opponent of the flagged side → claimant wins.
//   * claimant's OWN clock is dead (it's their turn) → claimant loses.
// Untimed games can never flag → 400.

export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ gameId: string }> },
) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }
  const { gameId } = await params;

  const { data: gameData, error: loadErr } = await supabaseAdmin
    .from('games')
    .select('*')
    .eq('id', gameId)
    .maybeSingle();
  if (loadErr) {
    console.error('[games/claim-flag] load failed', loadErr);
    return NextResponse.json({ error: 'lookup_failed' }, { status: 500 });
  }
  if (!gameData) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }
  const game = gameData as GameRow;

  if (game.status !== 'active') {
    return NextResponse.json({ error: 'not_active' }, { status: 409 });
  }
  if (userId !== game.white_id && userId !== game.black_id) {
    return NextResponse.json({ error: 'not_player' }, { status: 403 });
  }
  if (game.white_ms === null || game.black_ms === null) {
    return NextResponse.json({ error: 'not_timed' }, { status: 400 });
  }

  const now = Date.now();
  const turn = turnFromFen(game.fen);
  const clocks = remainingMs(
    {
      whiteMs: game.white_ms,
      blackMs: game.black_ms,
      lastMoveAt: game.last_move_at
        ? new Date(game.last_move_at).getTime()
        : null,
      turn,
      status: 'active',
    },
    now,
  );

  const moverBank = turn === 'w' ? clocks.whiteMs : clocks.blackMs;
  if (moverBank !== 0) {
    // The running clock still has time — no flag to claim.
    return NextResponse.json({ error: 'not_flagged' }, { status: 409 });
  }

  // The side to move flagged; the other side wins.
  const winnerId = turn === 'w' ? game.black_id : game.white_id;
  const result = turn === 'w' ? '0-1' : '1-0';

  const { data: ended, error: updErr } = await supabaseAdmin
    .from('games')
    .update({
      status: 'finished',
      result,
      winner_id: winnerId,
      end_reason: 'flag',
      draw_offer_by: null,
      white_ms: clocks.whiteMs,
      black_ms: clocks.blackMs,
    })
    .eq('id', gameId)
    .eq('status', 'active')
    .select('*')
    .maybeSingle();
  if (updErr) {
    console.error('[games/claim-flag] update failed', updErr);
    return NextResponse.json({ error: 'flag_failed' }, { status: 500 });
  }
  if (!ended) {
    return NextResponse.json({ error: 'not_active' }, { status: 409 });
  }

  const payload = {
    gameId,
    result,
    winnerId,
    reason: 'flag' as const,
    status: 'finished' as const,
    whiteMs: clocks.whiteMs,
    blackMs: clocks.blackMs,
  };
  await broadcastGameEvent(gameId, 'game.end', payload);

  return NextResponse.json(payload, { status: 200 });
}
