import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { broadcastGameEvent } from '@/lib/live-game/broadcast';
import { applyMove, turnFromFen } from '@/lib/live-game/validate';
import { computeClocksAfterMove } from '@/lib/live-game/clocks';
import type { GameRow } from '@/lib/live-game/types';

// Online play (phase 2) — submit a move.
//
// Server-authoritative: turn is derived from the stored FEN, the move is
// re-validated with chess.js from that FEN, and clocks are computed from server
// timestamps. A move that arrives after the mover's bank is spent loses on time
// (flag) and is NOT applied.
//
// Atomicity note: the repo has no transaction/RPC helper, so the move-insert
// and games-update run sequentially (move row first). Acceptable for v1 per the
// phase-2 spec; a follow-up can wrap these in a single RPC.

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ gameId: string }> },
) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }
  const { gameId } = await params;

  let body: { uci?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'bad_json' }, { status: 400 });
  }
  const uci = typeof body.uci === 'string' ? body.uci.trim() : '';
  if (!uci) {
    return NextResponse.json({ error: 'missing_uci' }, { status: 400 });
  }

  const { data: gameData, error: loadErr } = await supabaseAdmin
    .from('games')
    .select('*')
    .eq('id', gameId)
    .maybeSingle();
  if (loadErr) {
    console.error('[games/move] load failed', loadErr);
    return NextResponse.json({ error: 'lookup_failed' }, { status: 500 });
  }
  if (!gameData) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }
  const game = gameData as GameRow;

  if (game.status !== 'active') {
    return NextResponse.json({ error: 'not_active' }, { status: 409 });
  }

  // Turn / player check.
  const turn = turnFromFen(game.fen);
  const moverId = turn === 'w' ? game.white_id : game.black_id;
  if (moverId !== userId) {
    return NextResponse.json({ error: 'not_your_turn' }, { status: 403 });
  }

  const now = Date.now();
  const lastMoveAt = game.last_move_at
    ? new Date(game.last_move_at).getTime()
    : null;
  const elapsed = lastMoveAt === null ? 0 : Math.max(0, now - lastMoveAt);

  // Clock/flag check BEFORE validating the move — a flagged player cannot move.
  const clocks = computeClocksAfterMove({
    whiteMs: game.white_ms,
    blackMs: game.black_ms,
    lastMoveAt,
    now,
    turn,
    incrementSec: game.increment_sec,
  });

  if (clocks.flagged) {
    const winnerId = turn === 'w' ? game.black_id : game.white_id;
    const result = turn === 'w' ? '0-1' : '1-0';
    const { data: ended } = await supabaseAdmin
      .from('games')
      .update({
        status: 'finished',
        result,
        winner_id: winnerId,
        end_reason: 'flag',
        white_ms: clocks.whiteMs,
        black_ms: clocks.blackMs,
      })
      .eq('id', gameId)
      .eq('status', 'active')
      .select('*')
      .maybeSingle();
    // Only broadcast if we were the one to finalise it (idempotent).
    if (ended) {
      await broadcastGameEvent(gameId, 'game.end', {
        gameId,
        result,
        winnerId,
        reason: 'flag',
        whiteMs: clocks.whiteMs,
        blackMs: clocks.blackMs,
      });
    }
    return NextResponse.json(
      {
        error: 'flagged',
        result,
        winnerId,
        reason: 'flag',
        whiteMs: clocks.whiteMs,
        blackMs: clocks.blackMs,
      },
      { status: 409 },
    );
  }

  // Validate the move against the stored FEN.
  const applied = applyMove(game.fen, uci);
  if (!applied.ok) {
    return NextResponse.json({ error: 'illegal_move' }, { status: 422 });
  }

  const newPly = game.ply + 1;

  // 1) Append the move row.
  const { error: moveErr } = await supabaseAdmin.from('game_moves').insert({
    game_id: gameId,
    ply: newPly,
    uci,
    san: applied.san,
    fen_after: applied.fenAfter,
    move_time_ms: elapsed,
  });
  if (moveErr) {
    console.error('[games/move] move insert failed', moveErr);
    return NextResponse.json({ error: 'move_write_failed' }, { status: 500 });
  }

  // 2) Update the game row (position, clocks, and terminal state if any).
  const gameOver = applied.gameOver;
  const winnerId = gameOver
    ? gameOver.result === '1-0'
      ? game.white_id
      : gameOver.result === '0-1'
        ? game.black_id
        : null
    : null;

  const update: Record<string, unknown> = {
    fen: applied.fenAfter,
    ply: newPly,
    white_ms: clocks.whiteMs,
    black_ms: clocks.blackMs,
    last_move_at: new Date(now).toISOString(),
    // Any move clears a standing draw offer (lichess rule).
    draw_offer_by: null,
  };
  if (gameOver) {
    update.status = 'finished';
    update.result = gameOver.result;
    update.winner_id = winnerId;
    update.end_reason = gameOver.reason;
  }

  const { error: gameUpdErr } = await supabaseAdmin
    .from('games')
    .update(update)
    .eq('id', gameId);
  if (gameUpdErr) {
    console.error('[games/move] game update failed', gameUpdErr);
    return NextResponse.json({ error: 'game_write_failed' }, { status: 500 });
  }

  const movePayload = {
    ply: newPly,
    uci,
    san: applied.san,
    fenAfter: applied.fenAfter,
    whiteMs: clocks.whiteMs,
    blackMs: clocks.blackMs,
    ...(gameOver ? { gameOver } : {}),
  };
  await broadcastGameEvent(gameId, 'game.move', movePayload);
  if (gameOver) {
    await broadcastGameEvent(gameId, 'game.end', {
      gameId,
      result: gameOver.result,
      winnerId,
      reason: gameOver.reason,
      whiteMs: clocks.whiteMs,
      blackMs: clocks.blackMs,
    });
  }

  return NextResponse.json(movePayload, { status: 200 });
}
