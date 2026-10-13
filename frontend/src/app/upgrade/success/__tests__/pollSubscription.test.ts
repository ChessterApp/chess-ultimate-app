import { describe, it, expect, vi } from 'vitest';
import { pollSubscription, POLL_INTERVAL_MS, POLL_TIMEOUT_MS } from '../pollSubscription';

// Virtual clock: sleep advances time instantly.
function clock() {
  let t = 0;
  return {
    now: () => t,
    sleep: vi.fn(async (ms: number) => {
      t += ms;
    }),
  };
}

describe('pollSubscription', () => {
  it('resolves active with the plan once the status flips', async () => {
    const c = clock();
    const fetchStatus = vi
      .fn()
      .mockResolvedValueOnce({ active: false, plan: null })
      .mockResolvedValueOnce({ active: false, plan: null })
      .mockResolvedValue({ active: true, plan: 'monthly' });

    const result = await pollSubscription({ fetchStatus, ...c });
    expect(result).toEqual({ status: 'active', plan: 'monthly' });
    expect(fetchStatus).toHaveBeenCalledTimes(3);
    expect(c.sleep).toHaveBeenCalledWith(POLL_INTERVAL_MS);
  });

  it('times out after ~60s when the subscription never activates', async () => {
    const c = clock();
    const fetchStatus = vi.fn().mockResolvedValue({ active: false, plan: null });

    const result = await pollSubscription({ fetchStatus, ...c });
    expect(result).toEqual({ status: 'timeout' });
    expect(c.now()).toBeLessThanOrEqual(POLL_TIMEOUT_MS);
    // One poll at t=0 plus one per 2s interval up to the deadline.
    expect(fetchStatus).toHaveBeenCalledTimes(POLL_TIMEOUT_MS / POLL_INTERVAL_MS + 1);
  });

  it('keeps retrying through fetch errors until the timeout', async () => {
    const c = clock();
    const fetchStatus = vi.fn().mockRejectedValue(new Error('network'));

    const result = await pollSubscription({ fetchStatus, ...c });
    expect(result).toEqual({ status: 'timeout' });
    expect(fetchStatus).toHaveBeenCalledTimes(POLL_TIMEOUT_MS / POLL_INTERVAL_MS + 1);
  });

  it('recovers after transient errors when the subscription activates', async () => {
    const c = clock();
    const fetchStatus = vi
      .fn()
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValue({ active: true });

    expect(await pollSubscription({ fetchStatus, ...c })).toEqual({ status: 'active', plan: null });
  });

  it('stops when aborted', async () => {
    const c = clock();
    const controller = new AbortController();
    const fetchStatus = vi.fn(async () => {
      controller.abort();
      return { active: false };
    });

    const result = await pollSubscription({ fetchStatus, ...c, signal: controller.signal });
    expect(result).toEqual({ status: 'timeout' });
    expect(fetchStatus).toHaveBeenCalledTimes(1);
  });
});
