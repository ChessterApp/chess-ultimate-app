import 'server-only';
import { NextRequest, NextResponse, after } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { broadcastGameEvent } from '@/lib/live-game/broadcast';
import { logLiveGameEvent, createStageTimer } from '@/lib/live-game/log';
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
// Latency (Stage A): the two independent writes (move-row insert + games update)
// run concurrently via Promise.all, and the Realtime broadcast is scheduled with
// `after()` so it is off the response critical path. Turn/legality validation
// still runs strictly before any write, so correctness is unchanged.

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ gameId: string }> },
) {
  const timer = createStageTimer();
  const { userId } = await auth();
  const { gameId } = await params;
  let ply: number | null = null;
  const log = (outcome: string) =>
    logLiveGameEvent({
      source: 'server',
      action: 'move',
      gameId,
      userId,
      ply,
      outcome,
      durationMs: timer.total(),
      stages: timer.stages,
    });
  timer.mark('auth');

  if (!userId) {
    log('unauthorized');
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  let body: { uci?: unknown };
  try {
    body = await req.json();
  } catch {
    log('bad_json');
    return NextResponse.json({ error: 'bad_json' }, { status: 400 });
  }
  const uci = typeof body.uci === 'string' ? body.uci.trim() : '';
  if (!uci) {
    log('missing_uci');
    return NextResponse.json({ error: 'missing_uci' }, { status: 400 });
  }

  const { data: gameData, error: loadErr } = await supabaseAdmin
    .from('games')
    .select('*')
    .eq('id', gameId)
    .maybeSingle();
  timer.mark('load');
  if (loadErr) {
    console.error('[games/move] load failed', loadErr);
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

  // Turn / player check.
  const turn = turnFromFen(game.fen);
  const moverId = turn === 'w' ? game.white_id : game.black_id;
  if (moverId !== userId) {
    log('not_your_turn');
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
    timer.mark('write');
    // Only broadcast if we were the one to finalise it (idempotent).
    if (ended) {
      after(() =>
        broadcastGameEvent(gameId, 'game.end', {
          gameId,
          result,
          winnerId,
          reason: 'flag',
          whiteMs: clocks.whiteMs,
          blackMs: clocks.blackMs,
        }),
      );
    }
    log('flagged');
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
    log('illegal_move');
    return NextResponse.json({ error: 'illegal_move' }, { status: 422 });
  }

  const newPly = game.ply + 1;
  ply = newPly;

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

  // The move-row insert and the games update touch different tables and are both
  // gated only by the validation above, so they can run concurrently. One fewer
  // sequential round trip on the move hot path.
  const [{ error: moveErr }, { error: gameUpdErr }] = await Promise.all([
    supabaseAdmin.from('game_moves').insert({
      game_id: gameId,
      ply: newPly,
      uci,
      san: applied.san,
      fen_after: applied.fenAfter,
      move_time_ms: elapsed,
    }),
    supabaseAdmin.from('games').update(update).eq('id', gameId),
  ]);
  timer.mark('write');
  if (moveErr) {
    console.error('[games/move] move insert failed', moveErr);
    log('move_write_failed');
    return NextResponse.json({ error: 'move_write_failed' }, { status: 500 });
  }
  if (gameUpdErr) {
    console.error('[games/move] game update failed', gameUpdErr);
    log('game_write_failed');
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
  after(() => broadcastGameEvent(gameId, 'game.move', movePayload));
  if (gameOver) {
    after(() =>
      broadcastGameEvent(gameId, 'game.end', {
        gameId,
        result: gameOver.result,
        winnerId,
        reason: gameOver.reason,
        whiteMs: clocks.whiteMs,
        blackMs: clocks.blackMs,
      }),
    );
  }

  log('ok');
  return NextResponse.json(movePayload, { status: 200 });
}
