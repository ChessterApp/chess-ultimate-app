import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { broadcastGameEvent } from '@/lib/live-game/broadcast';
import { remainingMs } from '@/lib/live-game/clocks';
import { turnFromFen } from '@/lib/live-game/validate';
import type { GameRow } from '@/lib/live-game/types';

// Online play (phase 4) — draw offers.
//
// body { action: 'offer' | 'accept' | 'decline' }.
//   * offer   — records the offering player in games.draw_offer_by, broadcasts
//               game.draw_offer.
//   * decline — clears any standing offer, broadcasts game.draw_decline.
//   * accept  — valid ONLY if the OTHER player has a standing offer; finishes
//               the game as a draw (result '1/2-1/2', winner NULL), broadcasts
//               game.end. Server-authoritative: the client never decides.

type DrawAction = 'offer' | 'accept' | 'decline';

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ gameId: string }> },
) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }
  const { gameId } = await params;

  let body: { action?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'bad_json' }, { status: 400 });
  }
  const action = body.action;
  if (action !== 'offer' && action !== 'accept' && action !== 'decline') {
    return NextResponse.json({ error: 'bad_action' }, { status: 400 });
  }
  const drawAction = action as DrawAction;

  const { data: gameData, error: loadErr } = await supabaseAdmin
    .from('games')
    .select('*')
    .eq('id', gameId)
    .maybeSingle();
  if (loadErr) {
    console.error('[games/draw] load failed', loadErr);
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

  // ── Accept: the other player must have a standing offer ─────────────────────
  if (drawAction === 'accept') {
    if (!game.draw_offer_by || game.draw_offer_by === userId) {
      return NextResponse.json({ error: 'no_offer' }, { status: 409 });
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

    const { data: ended, error: updErr } = await supabaseAdmin
      .from('games')
      .update({
        status: 'finished',
        result: '1/2-1/2',
        winner_id: null,
        end_reason: 'draw',
        draw_offer_by: null,
        white_ms: clocks.whiteMs,
        black_ms: clocks.blackMs,
      })
      .eq('id', gameId)
      .eq('status', 'active')
      .select('*')
      .maybeSingle();
    if (updErr) {
      console.error('[games/draw] accept update failed', updErr);
      return NextResponse.json({ error: 'draw_failed' }, { status: 500 });
    }
    if (!ended) {
      return NextResponse.json({ error: 'not_active' }, { status: 409 });
    }

    const payload = {
      gameId,
      result: '1/2-1/2',
      winnerId: null,
      reason: 'draw' as const,
      status: 'finished' as const,
      whiteMs: clocks.whiteMs,
      blackMs: clocks.blackMs,
    };
    await broadcastGameEvent(gameId, 'game.end', payload);
    return NextResponse.json(payload, { status: 200 });
  }

  // ── Decline: clear any standing offer ───────────────────────────────────────
  if (drawAction === 'decline') {
    const { error: updErr } = await supabaseAdmin
      .from('games')
      .update({ draw_offer_by: null })
      .eq('id', gameId)
      .eq('status', 'active');
    if (updErr) {
      console.error('[games/draw] decline update failed', updErr);
      return NextResponse.json({ error: 'draw_failed' }, { status: 500 });
    }
    await broadcastGameEvent(gameId, 'game.draw_decline', { gameId });
    return NextResponse.json({ action: 'decline' }, { status: 200 });
  }

  // ── Offer: record the offering player ───────────────────────────────────────
  const { error: updErr } = await supabaseAdmin
    .from('games')
    .update({ draw_offer_by: userId })
    .eq('id', gameId)
    .eq('status', 'active');
  if (updErr) {
    console.error('[games/draw] offer update failed', updErr);
    return NextResponse.json({ error: 'draw_failed' }, { status: 500 });
  }
  await broadcastGameEvent(gameId, 'game.draw_offer', { gameId, by: userId });
  return NextResponse.json({ action: 'offer', by: userId }, { status: 200 });
}
