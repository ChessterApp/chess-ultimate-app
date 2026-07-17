import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Run `after()` synchronously so the scheduled insert is observable in-test.
vi.mock('next/server', async () => {
  const actual = await vi.importActual<typeof import('next/server')>('next/server');
  return { ...actual, after: (fn: () => unknown) => { fn(); } };
});

const insertMock = vi.fn();
vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: { from: () => ({ insert: insertMock }) },
}));

import { logLiveGameEvent, createStageTimer } from '../log';

const flush = () => new Promise((r) => setTimeout(r, 0));

describe('logLiveGameEvent', () => {
  beforeEach(() => {
    insertMock.mockReset();
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('maps the entry to snake_case columns and inserts it', async () => {
    insertMock.mockResolvedValue({ error: null });
    logLiveGameEvent({
      source: 'server',
      action: 'move',
      gameId: 'g1',
      userId: 'u1',
      ply: 3,
      outcome: 'ok',
      durationMs: 42,
      stages: { auth: 1, load: 20 },
      detail: { foo: 'bar' },
    });
    await flush();
    expect(insertMock).toHaveBeenCalledWith({
      game_id: 'g1',
      user_id: 'u1',
      source: 'server',
      action: 'move',
      ply: 3,
      outcome: 'ok',
      duration_ms: 42,
      stages: { auth: 1, load: 20 },
      detail: { foo: 'bar' },
    });
    expect(console.error).not.toHaveBeenCalled();
  });

  it('defaults absent optional fields to null', async () => {
    insertMock.mockResolvedValue({ error: null });
    logLiveGameEvent({ source: 'client', action: 'presence_leave' });
    await flush();
    expect(insertMock).toHaveBeenCalledWith(
      expect.objectContaining({
        source: 'client',
        action: 'presence_leave',
        game_id: null,
        user_id: null,
        ply: null,
        outcome: null,
        duration_ms: null,
        stages: null,
        detail: null,
      }),
    );
  });

  it('degrades gracefully when the insert returns an error (table missing)', async () => {
    insertMock.mockResolvedValue({
      error: { message: 'relation "live_game_logs" does not exist' },
    });
    expect(() =>
      logLiveGameEvent({ source: 'server', action: 'move' }),
    ).not.toThrow();
    await flush();
    expect(console.error).toHaveBeenCalled();
  });

  it('degrades gracefully when the insert throws', async () => {
    insertMock.mockRejectedValue(new Error('network down'));
    expect(() =>
      logLiveGameEvent({ source: 'server', action: 'join' }),
    ).not.toThrow();
    await flush();
    expect(console.error).toHaveBeenCalled();
  });
});

describe('createStageTimer', () => {
  it('records marks and a total as non-negative numbers', () => {
    const t = createStageTimer();
    t.mark('auth');
    t.mark('load');
    expect(typeof t.stages.auth).toBe('number');
    expect(typeof t.stages.load).toBe('number');
    expect(t.stages.auth).toBeGreaterThanOrEqual(0);
    expect(t.total()).toBeGreaterThanOrEqual(0);
  });
});
