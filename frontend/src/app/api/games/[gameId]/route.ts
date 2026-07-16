import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { remainingMs } from '@/lib/live-game/clocks';
import { turnFromFen } from '@/lib/live-game/validate';
import type {
  GameRow,
  GameMoveRow,
  HydrationPayload,
} from '@/lib/live-game/types';

// Online play (phase 2) — hydration payload.
//
// Broadcast is transport, Postgres is truth: the client fetches this on every
// (re)connect. Mirrors the RLS read rule — a 'challenge' row is visible to any
// authenticated user (the accept screen needs it), otherwise only to a player.

export async function GET(
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
    console.error('[games/get] load failed', loadErr);
    return NextResponse.json({ error: 'lookup_failed' }, { status: 500 });
  }
  if (!gameData) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }
  const game = gameData as GameRow;

  const isPlayer = [
    game.creator_id,
    game.opponent_id,
    game.white_id,
    game.black_id,
  ].includes(userId);
  // Non-players can only see open challenges — anything else is hidden.
  if (game.status !== 'challenge' && !isPlayer) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }

  const clocks = remainingMs(
    {
      whiteMs: game.white_ms,
      blackMs: game.black_ms,
      lastMoveAt: game.last_move_at
        ? new Date(game.last_move_at).getTime()
        : null,
      turn: turnFromFen(game.fen),
      status: game.status,
    },
    Date.now(),
  );

  const { data: moveRows, error: movesErr } = await supabaseAdmin
    .from('game_moves')
    .select('*')
    .eq('game_id', gameId)
    .order('ply', { ascending: true });
  if (movesErr) {
    console.error('[games/get] moves load failed', movesErr);
    return NextResponse.json({ error: 'lookup_failed' }, { status: 500 });
  }
  const moves = (moveRows as GameMoveRow[] | null) ?? [];

  const isChallenge = game.status === 'challenge';
  const payload: HydrationPayload = {
    game: {
      id: game.id,
      status: game.status,
      colorChoice: game.color_choice,
      initialSec: game.initial_sec,
      incrementSec: game.increment_sec,
      fen: game.fen,
      ply: game.ply,
      whiteMs: clocks.whiteMs,
      blackMs: clocks.blackMs,
      result: game.result,
      winnerId: game.winner_id,
      endReason: game.end_reason,
      creatorId: game.creator_id,
      // Player identities only once the game has left 'challenge'.
      ...(isChallenge
        ? {}
        : {
            whiteId: game.white_id,
            blackId: game.black_id,
            opponentId: game.opponent_id,
          }),
    },
    moves: moves.map((m) => ({
      ply: m.ply,
      uci: m.uci,
      san: m.san,
      fenAfter: m.fen_after,
      moveTimeMs: m.move_time_ms,
    })),
  };

  return NextResponse.json(payload, { status: 200 });
}
