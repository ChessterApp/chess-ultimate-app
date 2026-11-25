/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useDailyPlan } from '../useDailyPlan';

const plan = (id: string) => ({
  kind: 'daily_plan',
  cards: [{ type: 'review_last_game', game_id: id, title: `game ${id}` }, { type: 'warmup' }],
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useDailyPlan — the plan is of now (tester 25.11: «Разбор последней партии» offered an old game)', () => {
  it('is asked again each time the home is shown, with the skeleton meanwhile', async () => {
    let n = 0;
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => plan(String(++n)) }));
    vi.stubGlobal('fetch', fetchMock);

    const { result, rerender } = renderHook(({ shown }: { shown: boolean }) => useDailyPlan(true, shown), {
      initialProps: { shown: true },
    });
    expect(result.current.status).toBe('loading');
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const first = result.current;

    // The first message of the session: the home is gone, and the plan read for it is spent.
    rerender({ shown: false });
    expect(result.current.status).toBe('loading');
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // A new session: the home again — asked anew, never the earlier plan for a frame.
    rerender({ shown: true });
    expect(result.current.status).toBe('loading');
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(result.current).not.toEqual(first);
  });

  it('is never asked for while off', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useDailyPlan(false, true));
    expect(result.current.status).toBe('off');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
