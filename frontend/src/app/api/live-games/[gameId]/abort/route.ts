import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { broadcastGameEvent } from '@/lib/live-game/broadcast';
import type { GameRow } from '@/lib/live-game/types';

// Online play (phase 4) — abort.
//
// Two legal cases (lichess rule):
//   * status='active' AND fewer than 2 plies played — either player may abort a
//     game that has barely started; no result is recorded.
//   * status='challenge' — the creator cancels their own un-accepted challenge.
// Everything else is 409. Aborting sets status='aborted', end_reason='abort',
// no winner/result. Broadcasts game.end with status 'aborted'.

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
    console.error('[games/abort] load failed', loadErr);
    return NextResponse.json({ error: 'lookup_failed' }, { status: 500 });
  }
  if (!gameData) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }
  const game = gameData as GameRow;

  // Which prior status are we conditioning the abort on?
  let guardStatus: 'active' | 'challenge';
  if (game.status === 'challenge') {
    if (userId !== game.creator_id) {
      return NextResponse.json({ error: 'not_creator' }, { status: 403 });
    }
    guardStatus = 'challenge';
  } else if (game.status === 'active') {
    if (userId !== game.white_id && userId !== game.black_id) {
      return NextResponse.json({ error: 'not_player' }, { status: 403 });
    }
    if (game.ply >= 2) {
      return NextResponse.json({ error: 'too_late' }, { status: 409 });
    }
    guardStatus = 'active';
  } else {
    return NextResponse.json({ error: 'not_abortable' }, { status: 409 });
  }

  const { data: ended, error: updErr } = await supabaseAdmin
    .from('games')
    .update({
      status: 'aborted',
      end_reason: 'abort',
      draw_offer_by: null,
    })
    .eq('id', gameId)
    .eq('status', guardStatus)
    .select('*')
    .maybeSingle();
  if (updErr) {
    console.error('[games/abort] update failed', updErr);
    return NextResponse.json({ error: 'abort_failed' }, { status: 500 });
  }
  if (!ended) {
    // Status changed under us (e.g. opponent moved / accepted).
    return NextResponse.json({ error: 'not_abortable' }, { status: 409 });
  }

  const payload = {
    gameId,
    result: null,
    winnerId: null,
    reason: 'abort' as const,
    status: 'aborted' as const,
    whiteMs: game.white_ms,
    blackMs: game.black_ms,
  };
  await broadcastGameEvent(gameId, 'game.end', payload);

  return NextResponse.json(payload, { status: 200 });
}
