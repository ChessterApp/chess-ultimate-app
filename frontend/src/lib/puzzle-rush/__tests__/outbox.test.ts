import { describe, it, expect, vi } from 'vitest';
import { OUTBOX_KEY, OUTBOX_MAX, dequeueFinish, enqueueFinish, flushOutbox, pendingFinishes, type KeyValueStore } from '../outbox';
import type { FinishRequest, FinishResponse } from '../types';

function memoryStore(): KeyValueStore & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => { data.set(k, v); },
    removeItem: (k) => { data.delete(k); },
  };
}

const body = (run_id: string): FinishRequest => ({
  run_id, mode: '3min', seed: '0123456789abcdef', started_at: '2026-10-12T10:00:00Z',
  ended_at: '2026-10-12T10:03:00Z', end_reason: 'timeout', attempts: [],
});
const ok = (b: FinishRequest) => Promise.resolve({ run_id: b.run_id } as FinishResponse);
const fail = (status?: number) => () => Promise.reject(Object.assign(new Error('x'), status ? { status } : {}));

describe('finish outbox', () => {
  it('queues per user and dequeues by run id', () => {
    const s = memoryStore();
    enqueueFinish(s, 'u1', body('a'));
    enqueueFinish(s, 'u2', body('b'));
    enqueueFinish(s, 'u1', body('a')); // re-queue replaces
    expect(pendingFinishes(s, 'u1').map((b) => b.run_id)).toEqual(['a']);
    dequeueFinish(s, 'a');
    expect(pendingFinishes(s, 'u1')).toEqual([]);
    dequeueFinish(s, 'b');
    expect(s.data.has(OUTBOX_KEY)).toBe(false);
  });

  it('resends on the next load and clears what the server accepted', async () => {
    const s = memoryStore();
    enqueueFinish(s, 'u1', body('a'));
    enqueueFinish(s, 'u1', body('b'));
    const send = vi.fn(ok);
    const sent = await flushOutbox(s, 'u1', send);
    expect(send.mock.calls.map(([b]) => b.run_id)).toEqual(['a', 'b']);
    expect(sent.map((r) => r.run_id)).toEqual(['a', 'b']);
    expect(pendingFinishes(s, 'u1')).toEqual([]);
  });

  it('keeps transient failures (network, 5xx, 401, 429) and drops permanent 4xx', async () => {
    const s = memoryStore();
    for (const id of ['net', 'e503', 'e401', 'e429', 'e400', 'e409']) enqueueFinish(s, 'u1', body(id));
    const status: Record<string, number | undefined> = { e503: 503, e401: 401, e429: 429, e400: 400, e409: 409 };
    await flushOutbox(s, 'u1', (b) => fail(status[b.run_id])());
    expect(pendingFinishes(s, 'u1').map((b) => b.run_id)).toEqual(['net', 'e503', 'e401', 'e429']);
  });

  it("never resends another account's runs", async () => {
    const s = memoryStore();
    enqueueFinish(s, 'u2', body('theirs'));
    const send = vi.fn(ok);
    await flushOutbox(s, 'u1', send);
    expect(send).not.toHaveBeenCalled();
    expect(pendingFinishes(s, 'u2')).toHaveLength(1);
  });

  it('is bounded and survives corrupt storage', () => {
    const s = memoryStore();
    for (let i = 0; i < OUTBOX_MAX + 5; i += 1) enqueueFinish(s, 'u1', body(`r${i}`));
    const ids = pendingFinishes(s, 'u1').map((b) => b.run_id);
    expect(ids).toHaveLength(OUTBOX_MAX);
    expect(ids[0]).toBe('r5');
    s.setItem(OUTBOX_KEY, '{nope');
    expect(pendingFinishes(s, 'u1')).toEqual([]);
  });
});
