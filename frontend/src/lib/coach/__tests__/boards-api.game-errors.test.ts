import { describe, it, expect, vi, afterEach } from 'vitest';
import { coachApi, CoachApiError } from '../boards-api';

// Seam audit 28.10: start / resign / takeback answered null on any failure — the reason Hermes gave was lost.
function respond(status: number, body: unknown) {
  globalThis.fetch = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  ) as typeof fetch;
}

async function rejection(p: Promise<unknown>): Promise<CoachApiError> {
  try {
    await p;
  } catch (err) {
    return err as CoachApiError;
  }
  throw new Error('expected a rejection');
}

describe('coachApi game actions — the failure reason', () => {
  const realFetch = globalThis.fetch;
  afterEach(() => {
    globalThis.fetch = realFetch;
  });

  it('startGame: the engine being down comes back as engine_unavailable', async () => {
    respond(503, { error: 'Hermes error: 503', detail: { detail: 'The engine is unavailable: timeout' } });
    const err = await rejection(coachApi.startGame('s1', { color: 'white', elo: 1200 }));
    expect(err).toBeInstanceOf(CoachApiError);
    expect(err.code).toBe('engine_unavailable');
  });

  it("gameTakeback: Hermes's «Nothing to take back.» is kept", async () => {
    respond(400, { error: 'Hermes error: 400', detail: { detail: 'Nothing to take back.' } });
    const err = await rejection(coachApi.gameTakeback('s1', 'g1'));
    expect(err.code).toBe('nothing_to_take_back');
  });

  it('gameResign: a game already over is game_over', async () => {
    respond(400, { error: 'Hermes error: 400', detail: { detail: 'The game is over.' } });
    const err = await rejection(coachApi.gameResign('s1', 'g1'));
    expect(err.code).toBe('game_over');
  });

  it('a network failure is unreachable, still a CoachApiError', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch')) as typeof fetch;
    const err = await rejection(coachApi.gameResign('s1', 'g1'));
    expect(err).toBeInstanceOf(CoachApiError);
    expect(err.code).toBe('unreachable');
  });

  it('the proxy unable to reach Hermes (502) is unreachable', async () => {
    respond(502, { error: 'fetch failed' });
    expect((await rejection(coachApi.startGame('s1', { color: 'white', elo: 1200 }))).code).toBe('unreachable');
  });

  it("gameMove: Hermes's illegal-move refusal is illegal_move, its text kept for the console", async () => {
    respond(400, { error: 'Hermes error: 400', detail: { detail: 'e9 is not a legal move here.' } });
    const err = await rejection(coachApi.gameMove('s1', 'g1', 'e9'));
    expect(err.code).toBe('illegal_move');
    expect(err.message).toBe('e9 is not a legal move here.');
  });

  it("the proxy's own 401 is unauthorized", async () => {
    respond(401, { error: 'Unauthorized' });
    expect((await rejection(coachApi.gameResign('s1', 'g1'))).code).toBe('unauthorized');
  });
});
