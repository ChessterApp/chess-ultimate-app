/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { MISS, MULTI, NEXT, SOLVE, matePack } from '@/lib/puzzle-rush/__tests__/fixtures';
import { OUTBOX_KEY } from '@/lib/puzzle-rush/outbox';
import type { RushPuzzle } from '@/lib/puzzle-rush/types';

const play = vi.fn();
vi.mock('@/hooks/useSoundEffects', () => ({ useSoundEffects: () => ({ play }) }));
const clerk = { isSignedIn: false, userId: null as string | null, getToken: async () => null as string | null };
vi.mock('@clerk/nextjs', () => ({ useAuth: () => clerk }));

import { usePuzzleRush, TIMINGS } from '../usePuzzleRush';

const COUNTDOWN = TIMINGS.COUNTDOWN_LEAD_IN + 3 * TIMINGS.COUNTDOWN_STEP;
const T0 = Date.parse('2026-10-12T10:00:00Z');

const fetchMock = vi.fn();
function respond(status: number, body: unknown) {
  fetchMock.mockImplementationOnce(async () =>
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
}
const packOf = (puzzles: RushPuzzle[], from = 0) => ({ seed: 'x', from, count: puzzles.length, puzzles });
/** A full 40-puzzle pack starting with the two real Lichess puzzles. */
const FIRST = [MULTI, NEXT, ...matePack(38, 2)];
const urls = () => fetchMock.mock.calls.map(([u]) => String(u));
const tick = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date', 'performance'] });
  vi.setSystemTime(T0);
  localStorage.clear();
  play.mockReset();
  fetchMock.mockReset();
  Object.assign(clerk, { isSignedIn: false, userId: null, getToken: async () => null });
  global.fetch = fetchMock as unknown as typeof fetch;
});
afterEach(() => vi.useRealTimers());

/** Mount (prefetching `first`), start a run, and play through the countdown. */
async function playingRun(first: RushPuzzle[] = FIRST, next: RushPuzzle[] = matePack(40)) {
  respond(200, packOf(first));
  respond(200, packOf(next)); // Play Again pack, fetched during the countdown
  const hook = renderHook(() => usePuzzleRush('3min'));
  await act(async () => { await hook.result.current.start('3min'); });
  await tick(COUNTDOWN);
  return hook;
}

function move(hook: Awaited<ReturnType<typeof playingRun>>, uci: string) {
  act(() => { hook.result.current.onMove(uci.slice(0, 2) as never, uci.slice(2, 4) as never, uci[4]); });
}

/**
 * Clear the badge hold, then board clear + fade-in, so the next puzzle is
 * playable. Two acts: React commits ADVANCE (which arms the fade-in timers)
 * only when the first act ends.
 */
async function nextPuzzle() {
  await tick(TIMINGS.BADGE_HOLD_FAIL);
  await tick(TIMINGS.BOARD_CLEAR + TIMINGS.FADE_IN);
}

describe('usePuzzleRush', () => {
  it('prefetches the pack on mount; start needs no request; 3-2-1-Go! then the board unlocks', async () => {
    respond(200, packOf(FIRST));
    const { result } = renderHook(() => usePuzzleRush('3min'));
    await act(async () => {});
    expect(urls()).toHaveLength(1);
    expect(urls()[0]).toMatch(/^\/api\/puzzlerush\/pack\?seed=[0-9a-f]{16}&from=0&count=40$/);

    respond(200, packOf(matePack(40)));
    await act(async () => { await result.current.start('3min'); });
    expect(result.current.state.phase).toBe('countdown');
    expect(localStorage.getItem('puzzleRush.lastMode')).toBe('3min');
    expect(urls()).toHaveLength(2); // only the Play Again prefetch

    await tick(TIMINGS.COUNTDOWN_LEAD_IN);
    expect(result.current.countdown).toBe(3);
    expect(result.current.state.covered).toBe(true);
    await tick(TIMINGS.REVEAL_IN_THREE);
    expect(result.current.state.covered).toBe(false); // pieces fade in during "3"
    await tick(TIMINGS.COUNTDOWN_STEP - TIMINGS.REVEAL_IN_THREE);
    expect(result.current.countdown).toBe(2);
    await tick(TIMINGS.COUNTDOWN_STEP);
    expect(result.current.countdown).toBe(1);
    expect(result.current.state.inputLocked).toBe(true);
    await tick(TIMINGS.COUNTDOWN_STEP);
    expect(result.current.countdown).toBe('go');
    expect(result.current.state.phase).toBe('playing');
    expect(result.current.state.inputLocked).toBe(false);
    expect(result.current.state.lastMove).toEqual(['f2', 'g3']);
    expect(result.current.state.startedAtMs).toBe(performance.now());
  });

  it('wrong move: ✕ + strike in the same update as the drop, clank, next puzzle after the §3 pipeline, no request', async () => {
    const hook = await playingRun();
    const { result } = hook;
    const before = urls().length;

    move(hook, 'h6h7');
    expect(result.current.state.badge).toEqual({ square: 'h7', kind: 'fail' });
    expect(result.current.state.strikes).toBe(1);
    expect(play).toHaveBeenCalledWith('clank');

    await tick(TIMINGS.BADGE_HOLD_FAIL);
    expect(result.current.state.puzzle).toEqual(NEXT);
    expect(result.current.state.covered).toBe(true);
    await tick(TIMINGS.BOARD_CLEAR + TIMINGS.FADE_IN);
    expect(result.current.state.inputLocked).toBe(false);
    expect(result.current.state.orientation).toBe('black');
    expect(result.current.state.lastMove).toEqual(['g5', 'e7']);
    expect(urls()).toHaveLength(before);
  });

  it('correct move: ✓ at once, the opponent reply after the 160 ms hold', async () => {
    const hook = await playingRun();
    const { result } = hook;
    move(hook, 'e6e7');
    expect(result.current.state.badge?.kind).toBe('ok');
    await tick(TIMINGS.BADGE_HOLD_OK);
    expect(result.current.state.lastMove).toEqual(['b2', 'b1']);
    expect(result.current.state.inputLocked).toBe(false);
    expect(result.current.state.puzzle).toEqual(MULTI);
  });

  it('3rd strike: results show in the same update, guest best recorded on-device, zero requests', async () => {
    const hook = await playingRun(matePack(40));
    const { result } = hook;
    const before = urls().length;
    move(hook, SOLVE);
    await nextPuzzle();
    for (let i = 0; i < 2; i += 1) {
      move(hook, MISS);
      await nextPuzzle();
    }
    expect(result.current.showResults).toBe(false);
    move(hook, MISS);
    expect(result.current.state.phase).toBe('over');
    expect(result.current.state.endReason).toBe('strikes');
    expect(result.current.showResults).toBe(true);
    expect(result.current.isPb).toBe(true);
    expect(result.current.guestBests?.['3min']).toMatchObject({ top_score: 1, best_today: 1 });
    expect(result.current.tiles.map((t) => t.solved)).toEqual([true, false, false, false]);
    expect(urls()).toHaveLength(before);

    act(() => result.current.closeResults());
    expect(result.current.showResults).toBe(false);
  });

  it('a guest run that does not beat the device best is not a PB', async () => {
    localStorage.setItem('puzzleRush.guestBests', JSON.stringify({ '3min': { top: 9, today: 0, day: '2000-01-01' } }));
    const hook = await playingRun(matePack(40));
    act(() => hook.result.current.quit());
    expect(hook.result.current.isPb).toBe(false);
    expect(hook.result.current.guestBests?.['3min'].top_score).toBe(9);
  });

  it('timeout: the local clock ends the run exactly at the deadline', async () => {
    const hook = await playingRun();
    await tick(180_000 - 1);
    expect(hook.result.current.state.phase).toBe('playing');
    await tick(1);
    expect(hook.result.current.state.phase).toBe('over');
    expect(hook.result.current.state.endReason).toBe('timeout');
    expect(hook.result.current.showResults).toBe(true);
  });

  it('signed-in: one background POST /runs/finish at run end; ranks + PB merge in; outbox cleared', async () => {
    Object.assign(clerk, { isSignedIn: true, userId: 'user_a', getToken: async () => 'jwt-a' });
    const hook = await playingRun(matePack(40));
    const { result } = hook;
    move(hook, SOLVE);
    await nextPuzzle();

    let resolve!: (r: Response) => void;
    fetchMock.mockImplementationOnce(() => new Promise<Response>((r) => { resolve = r; }));
    act(() => result.current.quit());
    expect(result.current.showResults).toBe(true);
    expect(result.current.ranksPending).toBe(true);
    await act(async () => {}); // the request awaits getToken() before fetch
    expect(result.current.isPb).toBe(false);

    const [url, init] = fetchMock.mock.calls.at(-1)!;
    expect(String(url)).toMatch(/^\/api\/puzzlerush\/runs\/finish\?tz=/);
    expect((init as RequestInit).headers).toMatchObject({ Authorization: 'Bearer jwt-a' });
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body).toMatchObject({ mode: '3min', end_reason: 'quit', run_id: result.current.state.runId });
    expect(body.attempts.map((a: { result: string }) => a.result)).toEqual(['solved', 'unfinished']);
    expect(JSON.parse(localStorage.getItem(OUTBOX_KEY)!)).toHaveLength(1);

    await act(async () => {
      resolve(new Response(JSON.stringify({
        run_id: body.run_id, duplicate: false, score: 1, is_new_pb: true, longest_streak: 1,
        highest_solved_rating: 400, avg_ms_per_puzzle: 1000, duration_ms: 1000,
        personal_rank: 1, global_rank: { daily: 2, weekly: 3, all: 4 },
      }), { status: 200 }));
    });
    expect(result.current.isPb).toBe(true);
    expect(result.current.ranksPending).toBe(false);
    expect(result.current.recorded).toBe(true);
    expect(result.current.state.results?.global_rank).toEqual({ daily: 2, weekly: 3, all: 4 });
    expect(localStorage.getItem(OUTBOX_KEY)).toBeNull();
  });

  it('signed-in: a failed /finish stays in the outbox and is resent on the next page load', async () => {
    Object.assign(clerk, { isSignedIn: true, userId: 'user_a', getToken: async () => 'jwt-a' });
    const hook = await playingRun(matePack(40));
    respond(503, { error: 'finish_unavailable' });
    await act(async () => { hook.result.current.quit(); });
    expect(hook.result.current.recorded).toBe(false);
    const queued = JSON.parse(localStorage.getItem(OUTBOX_KEY)!);
    expect(queued).toHaveLength(1);
    hook.unmount();

    respond(200, { run_id: queued[0].body.run_id });
    respond(200, packOf(matePack(40)));
    await act(async () => { renderHook(() => usePuzzleRush('3min')); });
    const resent = fetchMock.mock.calls.find(([u], i) => String(u).includes('/runs/finish') && i >= 3);
    expect(JSON.parse((resent![1] as RequestInit).body as string).run_id).toBe(queued[0].body.run_id);
    expect(localStorage.getItem(OUTBOX_KEY)).toBeNull();
  });

  it('Play Again starts instantly from the pack prefetched during the previous countdown', async () => {
    const hook = await playingRun(FIRST, matePack(40));
    act(() => hook.result.current.quit());
    respond(200, packOf(matePack(40)));
    const before = urls().length;
    await act(async () => { await hook.result.current.start('3min'); });
    expect(hook.result.current.state.phase).toBe('countdown');
    expect(hook.result.current.state.puzzle?.id).toBe('M0');
    expect(urls()).toHaveLength(before + 1); // just the next Play Again prefetch
  });

  it('tops the pack up in the background when < 15 puzzles remain, retrying silently', async () => {
    const hook = await playingRun(matePack(16));
    expect(urls().some((u) => u.includes('from=16'))).toBe(false);
    respond(500, {});
    respond(200, packOf(matePack(40, 16), 16));
    move(hook, SOLVE); // index 1 next: 14 left → top-up
    await nextPuzzle();
    expect(urls().filter((u) => u.includes('from=16'))).toHaveLength(1);
    await tick(1000);
    expect(urls().filter((u) => u.includes('from=16'))).toHaveLength(2);
    expect(hook.result.current.state.pack).toHaveLength(56);
  });

  it('a pack that cannot be fetched surfaces a start error', async () => {
    respond(503, {});
    const { result } = renderHook(() => usePuzzleRush('5min'));
    respond(503, {});
    await act(async () => { await result.current.start('5min'); });
    expect(result.current.state.phase).toBe('idle');
    expect(result.current.state.error).toBe('network');
  });
});
