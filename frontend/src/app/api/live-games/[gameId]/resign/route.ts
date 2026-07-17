import 'server-only';
import { NextRequest, NextResponse, after } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { broadcastGameEvent } from '@/lib/live-game/broadcast';
import { logLiveGameEvent, createStageTimer } from '@/lib/live-game/log';
import { remainingMs } from '@/lib/live-game/clocks';
import { turnFromFen } from '@/lib/live-game/validate';
import type { GameRow } from '@/lib/live-game/types';

// Online play (phase 4) — resign.
//
// Only a player of an 'active' game may resign; the opponent wins. Final clocks
// are settled server-side (the side to move is debited for the elapsed time) so
// the terminal banner is accurate. The conditional update on status='active' is
// the idempotency/race guard — only the request that flips the row broadcasts.

export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ gameId: string }> },
) {
  const timer = createStageTimer();
  const { userId } = await auth();
  const { gameId } = await params;
  const log = (outcome: string) =>
    logLiveGameEvent({
      source: 'server',
      action: 'resign',
      gameId,
      userId,
      outcome,
      durationMs: timer.total(),
      stages: timer.stages,
    });
  timer.mark('auth');
  if (!userId) {
    log('unauthorized');
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const { data: gameData, error: loadErr } = await supabaseAdmin
    .from('games')
    .select('*')
    .eq('id', gameId)
    .maybeSingle();
  timer.mark('load');
  if (loadErr) {
    console.error('[games/resign] load failed', loadErr);
    log('lookup_failed');
    return NextResponse.json({ error: 'lookup_failed' }, { status: 500 });
  }
  if (!gameData) {
    log('not_found');
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }
  const game = gameData as GameRow;

  if (game.status !== 'active') {
    log('not_active');
    return NextResponse.json({ error: 'not_active' }, { status: 409 });
  }
  if (userId !== game.white_id && userId !== game.black_id) {
    log('not_player');
    return NextResponse.json({ error: 'not_player' }, { status: 403 });
  }

  const now = Date.now();
  const clocks = remainingMs(
    {
      whiteMs: game.white_ms,
      blackMs: game.black_ms,
      lastMoveAt: game.last_move_at
        ? new Date(game.last_move_at).getTime()
        : null,
      turn: turnFromFen(game.fen),
      status: 'active',
    },
    now,
  );

  const resignerIsWhite = userId === game.white_id;
  const winnerId = resignerIsWhite ? game.black_id : game.white_id;
  const result = resignerIsWhite ? '0-1' : '1-0';

  const { data: ended, error: updErr } = await supabaseAdmin
    .from('games')
    .update({
      status: 'finished',
      result,
      winner_id: winnerId,
      end_reason: 'resign',
      draw_offer_by: null,
      white_ms: clocks.whiteMs,
      black_ms: clocks.blackMs,
    })
    .eq('id', gameId)
    .eq('status', 'active')
    .select('*')
    .maybeSingle();
  timer.mark('write');
  if (updErr) {
    console.error('[games/resign] update failed', updErr);
    log('resign_failed');
    return NextResponse.json({ error: 'resign_failed' }, { status: 500 });
  }
  if (!ended) {
    // Someone finalised the game between our read and write.
    log('not_active');
    return NextResponse.json({ error: 'not_active' }, { status: 409 });
  }

  const payload = {
    gameId,
    result,
    winnerId,
    reason: 'resign' as const,
    status: 'finished' as const,
    whiteMs: clocks.whiteMs,
    blackMs: clocks.blackMs,
  };
  after(() => broadcastGameEvent(gameId, 'game.end', payload));

  log('ok');
  return NextResponse.json(payload, { status: 200 });
}
