import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { logLiveGameEvent, createStageTimer } from '@/lib/live-game/log';
import type { ColorChoice } from '@/lib/live-game/types';

// Online play (phase 2) — create a challenge link.
//
// One row is both the challenge and the eventual live game (challenge id ==
// game id). Only the creator's own INSERT is allowed here; everything after
// accept is a service-role write on other routes.

const VALID_COLORS = new Set<ColorChoice>(['white', 'black', 'random']);
const CHALLENGE_TTL_MS = 24 * 60 * 60 * 1000;

function isValidTimeControl(v: unknown): v is number | undefined | null {
  return v == null || (typeof v === 'number' && Number.isInteger(v) && v >= 0);
}

export async function POST(req: NextRequest) {
  const timer = createStageTimer();
  const { userId } = await auth();
  let gameId: string | null = null;
  const log = (outcome: string) =>
    logLiveGameEvent({
      source: 'server',
      action: 'challenge',
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

  let body: {
    colorChoice?: unknown;
    initialSec?: unknown;
    incrementSec?: unknown;
  };
  try {
    body = await req.json();
  } catch {
    log('bad_json');
    return NextResponse.json({ error: 'bad_json' }, { status: 400 });
  }

  const colorChoice = body.colorChoice as ColorChoice | undefined;
  if (!colorChoice || !VALID_COLORS.has(colorChoice)) {
    log('invalid_color');
    return NextResponse.json({ error: 'invalid_color' }, { status: 400 });
  }
  if (!isValidTimeControl(body.initialSec) || !isValidTimeControl(body.incrementSec)) {
    log('invalid_time_control');
    return NextResponse.json({ error: 'invalid_time_control' }, { status: 400 });
  }

  // Untimed unless a positive initial time is supplied.
  const initialSec =
    typeof body.initialSec === 'number' && body.initialSec > 0
      ? body.initialSec
      : null;
  const incrementSec =
    initialSec !== null && typeof body.incrementSec === 'number'
      ? body.incrementSec
      : null;

  const { data, error } = await supabaseAdmin
    .from('games')
    .insert({
      creator_id: userId,
      status: 'challenge',
      color_choice: colorChoice,
      initial_sec: initialSec,
      increment_sec: incrementSec,
      expires_at: new Date(Date.now() + CHALLENGE_TTL_MS).toISOString(),
    })
    .select('id')
    .single();
  timer.mark('insert');

  if (error || !data) {
    console.error('[games/challenge] insert failed', error);
    log('create_failed');
    return NextResponse.json({ error: 'create_failed' }, { status: 500 });
  }

  gameId = (data as { id: string }).id;
  const url = `${new URL(req.url).origin}/play/live/${gameId}`;
  log('ok');
  return NextResponse.json({ gameId, url }, { status: 201 });
}
