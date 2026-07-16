import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { broadcastGameEvent } from '@/lib/live-game/broadcast';
import type { GameRow } from '@/lib/live-game/types';

// Online play (phase 2) — idempotent accept of a challenge.
//
// The conditional UPDATE (status 'challenge' → 'active') is the race guard: two
// simultaneous joiners both issue it, only one flips a row, the loser gets 0
// rows back → 409. Colors are resolved server-side and clocks initialised.

/** Deterministic coin flip from the game uuid (no RNG — reproducible). */
function creatorIsWhite(colorChoice: string, gameId: string): boolean {
  if (colorChoice === 'white') return true;
  if (colorChoice === 'black') return false;
  // 'random': parity of the summed hex nibbles of the uuid.
  let sum = 0;
  for (const ch of gameId.replace(/-/g, '')) {
    const n = parseInt(ch, 16);
    if (!Number.isNaN(n)) sum += n;
  }
  return sum % 2 === 0;
}

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
    console.error('[games/join] load failed', loadErr);
    return NextResponse.json({ error: 'lookup_failed' }, { status: 500 });
  }
  if (!gameData) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }
  const game = gameData as GameRow;

  if (game.creator_id === userId) {
    return NextResponse.json({ error: 'cannot_join_own' }, { status: 403 });
  }
  if (game.status !== 'challenge') {
    return NextResponse.json({ error: 'not_open' }, { status: 409 });
  }
  if (game.expires_at && new Date(game.expires_at).getTime() < Date.now()) {
    // Best-effort mark expired (only if still a challenge).
    await supabaseAdmin
      .from('games')
      .update({ status: 'expired' })
      .eq('id', gameId)
      .eq('status', 'challenge');
    return NextResponse.json({ error: 'expired' }, { status: 410 });
  }

  const creatorWhite = creatorIsWhite(game.color_choice, gameId);
  const whiteId = creatorWhite ? game.creator_id : userId;
  const blackId = creatorWhite ? userId : game.creator_id;
  const bankMs = game.initial_sec != null ? game.initial_sec * 1000 : null;
  const nowIso = new Date().toISOString();

  // Race guard: only the first joiner flips 'challenge' → 'active'.
  const { data: updated, error: updErr } = await supabaseAdmin
    .from('games')
    .update({
      status: 'active',
      opponent_id: userId,
      white_id: whiteId,
      black_id: blackId,
      white_ms: bankMs,
      black_ms: bankMs,
      last_move_at: nowIso,
    })
    .eq('id', gameId)
    .eq('status', 'challenge')
    .select('*')
    .maybeSingle();
  if (updErr) {
    console.error('[games/join] accept update failed', updErr);
    return NextResponse.json({ error: 'accept_failed' }, { status: 500 });
  }
  if (!updated) {
    // Someone else accepted between our read and write.
    return NextResponse.json({ error: 'already_taken' }, { status: 409 });
  }
  const row = updated as GameRow;

  await broadcastGameEvent(gameId, 'game.start', {
    gameId,
    status: row.status,
    fen: row.fen,
    whiteId: row.white_id,
    blackId: row.black_id,
    whiteMs: row.white_ms,
    blackMs: row.black_ms,
    lastMoveAt: row.last_move_at,
  });

  return NextResponse.json(
    {
      gameId,
      status: row.status,
      fen: row.fen,
      whiteId: row.white_id,
      blackId: row.black_id,
      whiteMs: row.white_ms,
      blackMs: row.black_ms,
    },
    { status: 200 },
  );
}
