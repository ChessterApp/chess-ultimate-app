/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { MULTI, NEXT, RESULTS, T0, created, moveRes } from '@/lib/puzzle-rush/__tests__/fixtures';

const play = vi.fn();
vi.mock('@/hooks/useSoundEffects', () => ({ useSoundEffects: () => ({ play }) }));
vi.mock('@clerk/nextjs', () => ({ useAuth: () => ({ isSignedIn: false, getToken: async () => null }) }));

import { usePuzzleRush, TIMINGS } from '../usePuzzleRush';

const fetchMock = vi.fn();
function respond(status: number, body: unknown) {
  fetchMock.mockImplementationOnce(async () =>
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
}
const iso = (ms: number) => new Date(ms).toISOString();
const tick = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] });
  vi.setSystemTime(T0);
  localStorage.clear();
  sessionStorage.clear();
  play.mockReset();
  fetchMock.mockReset();
  global.fetch = fetchMock as unknown as typeof fetch;
});
afterEach(() => vi.useRealTimers());

async function startedRun() {
  respond(201, created({ guest_token: 'guest-tok', server_now: iso(T0) }));
  const hook = renderHook(() => usePuzzleRush('3min'));
  await act(async () => { await hook.result.current.start('3min'); });
  return hook;
}

describe('usePuzzleRush', () => {
  it('runs 3-2-1-Go! aligned to the server start, then unlocks the board', async () => {
    const { result } = await startedRun();
    expect(result.current.state.phase).toBe('countdown');
    expect(localStorage.getItem('puzzleRush.lastMode')).toBe('3min');
    expect(sessionStorage.getItem('puzzleRush.guestToken')).toBe('guest-tok');

    // started_at is 3 s after create; 3 steps of 750 ms end exactly there.
    await tick(750);
    expect(result.current.countdown).toBe(3);
    expect(result.current.state.covered).toBe(true);
    await tick(TIMINGS.REVEAL_IN_THREE);
    expect(result.current.state.covered).toBe(false); // pieces fade in during "3"
    await tick(750 - TIMINGS.REVEAL_IN_THREE);
    expect(result.current.countdown).toBe(2);
    await tick(750);
    expect(result.current.countdown).toBe(1);
    expect(result.current.state.inputLocked).toBe(true);
    await tick(750);
    expect(result.current.countdown).toBe('go');
    expect(result.current.state.phase).toBe('playing');
    expect(result.current.state.inputLocked).toBe(false);
    expect(result.current.state.lastMove).toEqual(['f2', 'g3']);
  });

  it('wrong move: guest token header, clank, strike, next puzzle after the §3 pipeline', async () => {
    const { result } = await startedRun();
    await tick(3000);

    respond(200, moveRes({ result: 'wrong', strikes: 1, next_puzzle: NEXT }));
    await act(async () => { await result.current.onMove('h6', 'h7'); });
    const [, init] = fetchMock.mock.calls.at(-1)!;
    expect((init as RequestInit).headers).toMatchObject({ 'X-Guest-Token': 'guest-tok' });
    expect(play).toHaveBeenCalledWith('clank');
    expect(result.current.state.strikes).toBe(1);
    expect(result.current.state.badge?.kind).toBe('fail');

    await tick(TIMINGS.BADGE_HOLD_FAIL);
    expect(result.current.state.puzzle).toEqual(NEXT);
    expect(result.current.state.covered).toBe(true);
    await tick(TIMINGS.BOARD_CLEAR + TIMINGS.FADE_IN);
    expect(result.current.state.inputLocked).toBe(false);
    expect(result.current.state.orientation).toBe('black');
    expect(result.current.state.lastMove).toEqual(['g5', 'e7']);
  });

  it('applies the opponent reply after a correct move', async () => {
    const { result } = await startedRun();
    await tick(3000);
    respond(200, moveRes({ result: 'correct', reply: 'b2b1' }));
    await act(async () => { await result.current.onMove('e6', 'e7'); });
    expect(result.current.state.badge?.kind).toBe('ok');
    await tick(TIMINGS.BADGE_HOLD_OK);
    expect(result.current.state.lastMove).toEqual(['b2', 'b1']);
    expect(result.current.state.inputLocked).toBe(false);
    expect(result.current.state.puzzle).toEqual(MULTI);
  });

  it('timeout: at the deadline the server is asked and its result ends the run', async () => {
    const { result } = await startedRun();
    await tick(3000);
    // First poll lands a hair early (server not over yet), the retry is.
    respond(200, { run_over: false, attempts: [] });
    respond(200, {
      run_id: 'x', mode: '3min', run_over: true, end_reason: 'timeout', score: 6, strikes: 0, streak: 6,
      started_at: created().started_at, deadline: created().deadline, server_now: iso(T0 + 183_500),
      attempts: [], results: { ...RESULTS, score: 6 },
    });
    await tick(180_000);
    expect(result.current.state.phase).toBe('playing');
    await tick(TIMINGS.TIMEOUT_POLL);
    expect(result.current.state.phase).toBe('over');
    expect(result.current.state.endReason).toBe('timeout');
    expect(fetchMock.mock.calls.filter(([u]) => String(u).includes('/runs/1111')).length).toBe(2);

    // Results modal after the run-over delay; guest best recorded on-device as a PB.
    expect(result.current.showResults).toBe(false);
    await tick(TIMINGS.RESULTS_DELAY);
    expect(result.current.showResults).toBe(true);
    expect(result.current.isPb).toBe(true);
    expect(JSON.parse(localStorage.getItem('puzzleRush.guestBests')!)['3min'].top).toBe(6);
    expect(sessionStorage.getItem('puzzleRush.guestToken')).toBeNull();
  });

  it('a 409 run_over on a move ends the run with the body results', async () => {
    const { result } = await startedRun();
    await tick(3000);
    respond(409, { error: 'run_over', run_over: true, end_reason: 'timeout', score: 2, strikes: 1, results: { ...RESULTS, score: 2 } });
    await act(async () => { await result.current.onMove('e6', 'e7'); });
    expect(result.current.state.phase).toBe('over');
    expect(result.current.state.results?.score).toBe(2);
  });

  it('quit ends the run and keeps the score', async () => {
    const { result } = await startedRun();
    await tick(3000);
    respond(200, { ...moveRes({}), run_over: true, end_reason: 'quit', score: 0, results: { ...RESULTS, score: 0 } });
    await act(async () => { await result.current.quit(); });
    expect(result.current.state.phase).toBe('over');
    expect(result.current.state.endReason).toBe('quit');
    expect(String(fetchMock.mock.calls.at(-1)![0])).toContain('/quit');
  });

  it('START_FAILED surfaces a rate limit', async () => {
    respond(429, { error: 'rate_limited' });
    const { result } = renderHook(() => usePuzzleRush('5min'));
    await act(async () => { await result.current.start('5min'); });
    expect(result.current.state.phase).toBe('idle');
    expect(result.current.state.error).toBe('rate_limited');
  });
});
