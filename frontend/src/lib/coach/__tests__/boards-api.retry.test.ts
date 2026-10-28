import { describe, it, expect, vi, afterEach } from 'vitest';
import { coachApi } from '../boards-api';

// Review 28.10: Hermes answers 503 when a session could not be read back from Supabase (instead of running it
// without its game); the page asks again rather than showing no restored game until a reload.
describe('session restore after a 503', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('asks again and gets the boards', async () => {
    vi.useFakeTimers();
    const boards = { active_board_id: 'b1', boards: [] };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({ error: 'session could not be loaded' }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => boards });
    vi.stubGlobal('fetch', fetchMock);
    const pending = coachApi.listBoards('s1');
    await vi.advanceTimersByTimeAsync(1000);
    expect(await pending).toEqual(boards);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('gives up after its retries (a plain failure, not «session not found»)', async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) });
    vi.stubGlobal('fetch', fetchMock);
    const pending = coachApi.listBoards('s1');
    await vi.advanceTimersByTimeAsync(5000);
    expect(await pending).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
