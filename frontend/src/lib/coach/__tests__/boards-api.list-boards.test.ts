import { describe, it, expect, vi, afterEach } from 'vitest';
import { coachApi, SESSION_NOT_FOUND } from '../boards-api';

function respond(status: number, body: unknown) {
  globalThis.fetch = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  ) as typeof fetch;
}

describe('coachApi.listBoards', () => {
  const realFetch = globalThis.fetch;
  afterEach(() => {
    globalThis.fetch = realFetch;
  });

  it('returns the boards on success', async () => {
    respond(200, { active_board_id: 'b1', boards: [] });
    expect(await coachApi.listBoards('s1')).toEqual({ active_board_id: 'b1', boards: [] });
  });

  it("reports Hermes's 'Session not found' 404 (unknown or another user's session)", async () => {
    respond(404, { error: 'Hermes error: 404', detail: { detail: 'Session not found' } });
    expect(await coachApi.listBoards('s1')).toBe(SESSION_NOT_FOUND);
  });

  it('treats a 404 from a Hermes without the route as a plain failure', async () => {
    respond(404, { error: 'Hermes error: 404', detail: { detail: 'Not Found' } });
    expect(await coachApi.listBoards('s1')).toBeNull();
  });

  it('treats a 5xx as a plain failure', async () => {
    respond(502, { error: 'fetch failed' });
    expect(await coachApi.listBoards('s1')).toBeNull();
  });

  it('treats a network error as a plain failure', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('offline')) as typeof fetch;
    expect(await coachApi.listBoards('s1')).toBeNull();
  });
});
