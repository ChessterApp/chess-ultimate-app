import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const { capture, shutdown, ctor } = vi.hoisted(() => ({
  capture: vi.fn(),
  shutdown: vi.fn(),
  ctor: vi.fn(),
}));
vi.mock('posthog-node', () => ({
  PostHog: class {
    constructor(...args: unknown[]) {
      ctor(...args);
    }
    capture = capture;
    shutdown = shutdown;
  },
}));

import { captureServer, POSTHOG_CAPTURE_HOST } from '../server';
import { ANALYTICS_EVENTS } from '../events';

describe('captureServer()', () => {
  beforeEach(() => {
    capture.mockReset();
    shutdown.mockReset().mockResolvedValue(undefined);
    ctor.mockReset();
    vi.stubEnv('NEXT_PUBLIC_POSTHOG_KEY', 'phc_test');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('captures with serverless flush settings and awaits shutdown', async () => {
    await captureServer('user_1', ANALYTICS_EVENTS.USER_SIGNED_UP, { method: 'google' });
    expect(ctor).toHaveBeenCalledWith('phc_test', {
      host: POSTHOG_CAPTURE_HOST,
      flushAt: 1,
      flushInterval: 0,
    });
    expect(capture).toHaveBeenCalledWith({
      distinctId: 'user_1',
      event: 'user_signed_up',
      properties: { method: 'google' },
    });
    expect(shutdown).toHaveBeenCalledTimes(1);
  });

  it('scrubs PII, including nested $set props', async () => {
    await captureServer('user_1', ANALYTICS_EVENTS.USER_SIGNED_UP, {
      email: 'a@b.c',
      phone: '+7',
      birthday: '2015-01-01',
      $set: { path: 'kids', dob: '2015-01-01' },
    });
    expect(capture.mock.calls[0][0].properties).toEqual({ $set: { path: 'kids' } });
  });

  it('is a no-op without a key', async () => {
    vi.stubEnv('NEXT_PUBLIC_POSTHOG_KEY', '');
    await captureServer('user_1', ANALYTICS_EVENTS.USER_SIGNED_UP);
    expect(ctor).not.toHaveBeenCalled();
  });

  it('is a no-op without a distinct id', async () => {
    await captureServer(undefined, ANALYTICS_EVENTS.USER_SIGNED_UP);
    expect(ctor).not.toHaveBeenCalled();
  });

  it('never throws when PostHog fails', async () => {
    shutdown.mockRejectedValue(new Error('network down'));
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    await expect(
      captureServer('user_1', ANALYTICS_EVENTS.USER_SIGNED_UP),
    ).resolves.toBeUndefined();
  });
});
