import 'server-only';

/**
 * Server-side telemetry logger for online play. Writes one row to
 * `public.live_game_logs` per request/event via the service-role client.
 *
 * Contract: this is fire-and-forget and MUST NOT throw or block the response.
 * It schedules the insert with Next's `after()` so the write happens after the
 * response is flushed, and swallows every error (also `console.error`ing it) so
 * a missing table or a failed insert can never break a live game. Applying the
 * `live_game_logs` migration is therefore a diagnosability upgrade, not a hard
 * runtime dependency.
 */

import { after } from 'next/server';
import { supabaseAdmin } from '@/lib/supabase-admin';

export type LogSource = 'server' | 'client';

export interface LiveGameLogEntry {
  source: LogSource;
  action: string;
  gameId?: string | null;
  userId?: string | null;
  ply?: number | null;
  /** 'ok' or an error code. */
  outcome?: string | null;
  durationMs?: number | null;
  /** Per-stage timings, ms (e.g. { auth: 3, load: 40, write: 55 }). */
  stages?: Record<string, number> | null;
  detail?: Record<string, unknown> | null;
}

/**
 * Insert the log row. Isolated so it can be scheduled by `after()` and so every
 * failure mode (table missing, network, service-role misconfig) is contained.
 */
async function writeLog(entry: LiveGameLogEntry): Promise<void> {
  try {
    const { error } = await supabaseAdmin.from('live_game_logs').insert({
      game_id: entry.gameId ?? null,
      user_id: entry.userId ?? null,
      source: entry.source,
      action: entry.action,
      ply: entry.ply ?? null,
      outcome: entry.outcome ?? null,
      duration_ms: entry.durationMs ?? null,
      stages: entry.stages ?? null,
      detail: entry.detail ?? null,
    });
    if (error) {
      console.error('[live-game log] insert failed', error);
    }
  } catch (err) {
    // Table missing / network / anything else — never propagate.
    console.error('[live-game log] insert threw', err);
  }
}

/** Fire-and-forget structured log for a live-game request or client event. */
export function logLiveGameEvent(entry: LiveGameLogEntry): void {
  try {
    after(() => writeLog(entry));
  } catch {
    // Called outside a request scope (e.g. unit tests) — still non-blocking.
    void writeLog(entry);
  }
}

/**
 * Per-request stage timer. `mark(name)` records the ms elapsed since the last
 * mark (or since construction) under `name`; `total()` is ms since construction.
 * Used by route handlers to populate the `stages` jsonb + `duration_ms`.
 */
export function createStageTimer() {
  const start = performance.now();
  let last = start;
  const stages: Record<string, number> = {};
  return {
    stages,
    mark(name: string): void {
      const now = performance.now();
      stages[name] = Math.round(now - last);
      last = now;
    },
    total(): number {
      return Math.round(performance.now() - start);
    },
  };
}
