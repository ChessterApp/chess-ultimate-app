/**
 * Table-driven supabaseAdmin mock for the online-play route tests. Mirrors the
 * builder pattern used by src/app/api/promo/redeem/__tests__/route.test.ts, but
 * shared across the four `games` routes and extended with `insert` / `order`.
 *
 * Usage in a test file:
 *   vi.mock('@/lib/supabase-admin', async () => {
 *     const m = await import('@/test/liveGameSupabaseMock');
 *     return { supabaseAdmin: { from: (t: string) => m.makeBuilder(t) } };
 *   });
 *   import { scripts, recorded, resetSupabaseMock } from '@/test/liveGameSupabaseMock';
 *
 * Then script per-`${table}.${op}` responses, e.g.
 *   scripts['games.select'] = [{ data: gameRow, error: null }];
 */

export interface ScriptedResponse {
  data?: unknown;
  error?: unknown;
}

export interface Recorded {
  table: string;
  op: string;
  payload?: unknown;
  filters: Array<[string, unknown]>;
}

export const recorded: Recorded[] = [];
export const scripts: Record<string, ScriptedResponse[]> = {};

export function resetSupabaseMock(): void {
  recorded.length = 0;
  for (const k of Object.keys(scripts)) delete scripts[k];
}

function nextScript(table: string, op: string): ScriptedResponse {
  const queue = scripts[`${table}.${op}`];
  if (!queue || queue.length === 0) return { data: null, error: null };
  return queue.shift() as ScriptedResponse;
}

export function makeBuilder(table: string) {
  const rec: Recorded = { table, op: '', filters: [] };
  let pushed = false;

  const finalize = (op: string) => {
    rec.op = op;
    if (!pushed) {
      recorded.push(rec);
      pushed = true;
    }
    return Promise.resolve(nextScript(table, op));
  };

  const chain: Record<string, unknown> = {
    select(_cols?: string) {
      rec.op = rec.op || 'select';
      return chain;
    },
    insert(payload: unknown) {
      rec.op = 'insert';
      rec.payload = payload;
      return chain;
    },
    update(payload: unknown) {
      rec.op = 'update';
      rec.payload = payload;
      return chain;
    },
    eq(col: string, val: unknown) {
      rec.filters.push([col, val]);
      return chain;
    },
    order(_col: string, _opts?: unknown) {
      return finalize(rec.op || 'select');
    },
    maybeSingle() {
      return finalize(rec.op || 'select');
    },
    single() {
      return finalize(rec.op || 'select');
    },
    // PromiseLike — enables a bare `await supabase.from(...).insert(...)` etc.
    then(
      onFulfilled: (v: ScriptedResponse) => unknown,
      onRejected?: (e: unknown) => unknown,
    ) {
      return finalize(rec.op || 'select').then(onFulfilled, onRejected);
    },
  };
  return chain;
}
