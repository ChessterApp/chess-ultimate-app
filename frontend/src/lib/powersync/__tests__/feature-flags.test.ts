import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('feature flags', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    vi.resetModules();
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it('defaults all flags to false when env vars are not set', async () => {
    delete process.env.NEXT_PUBLIC_POWERSYNC_ENABLED;
    delete process.env.NEXT_PUBLIC_LOCAL_FIRST_GAMES;
    delete process.env.NEXT_PUBLIC_LOCAL_FIRST_REPERTOIRE;
    delete process.env.NEXT_PUBLIC_ENHANCED_SW;
    delete process.env.NEXT_PUBLIC_SMART_SERVICE_WORKER;
    delete process.env.NEXT_PUBLIC_PREFETCH_QUEUE;
    delete process.env.NEXT_PUBLIC_SYNC_INDICATOR;
    delete process.env.NEXT_PUBLIC_OFFLINE_MODE;

    const flags = await import('../../feature-flags');

    expect(flags.POWERSYNC_ENABLED).toBe(false);
    expect(flags.LOCAL_FIRST_GAMES).toBe(false);
    expect(flags.LOCAL_FIRST_REPERTOIRE).toBe(false);
    expect(flags.ENHANCED_SW).toBe(false);
    expect(flags.SMART_SERVICE_WORKER).toBe(false);
    expect(flags.PREFETCH_QUEUE).toBe(false);
    expect(flags.SYNC_INDICATOR).toBe(false);
    expect(flags.OFFLINE_MODE).toBe(false);
  });

  it('enables POWERSYNC_ENABLED when env var is "true"', async () => {
    process.env.NEXT_PUBLIC_POWERSYNC_ENABLED = 'true';

    const flags = await import('../../feature-flags');

    expect(flags.POWERSYNC_ENABLED).toBe(true);
  });

  it('keeps POWERSYNC_ENABLED false for non-"true" values', async () => {
    process.env.NEXT_PUBLIC_POWERSYNC_ENABLED = 'false';
    const flags1 = await import('../../feature-flags');
    expect(flags1.POWERSYNC_ENABLED).toBe(false);
  });

  it('enables individual flags independently', async () => {
    delete process.env.NEXT_PUBLIC_POWERSYNC_ENABLED;
    delete process.env.NEXT_PUBLIC_LOCAL_FIRST_REPERTOIRE;
    delete process.env.NEXT_PUBLIC_ENHANCED_SW;
    delete process.env.NEXT_PUBLIC_SMART_SERVICE_WORKER;
    process.env.NEXT_PUBLIC_LOCAL_FIRST_GAMES = 'true';
    process.env.NEXT_PUBLIC_PREFETCH_QUEUE = 'true';

    const flags = await import('../../feature-flags');

    expect(flags.LOCAL_FIRST_GAMES).toBe(true);
    expect(flags.PREFETCH_QUEUE).toBe(true);
    expect(flags.POWERSYNC_ENABLED).toBe(false);
    expect(flags.LOCAL_FIRST_REPERTOIRE).toBe(false);
    expect(flags.ENHANCED_SW).toBe(false);
    expect(flags.SMART_SERVICE_WORKER).toBe(false);
  });

  it('enables SMART_SERVICE_WORKER when env var is "true"', async () => {
    process.env.NEXT_PUBLIC_SMART_SERVICE_WORKER = 'true';

    const flags = await import('../../feature-flags');

    expect(flags.SMART_SERVICE_WORKER).toBe(true);
    expect(flags.ENHANCED_SW).toBe(false);
  });

  it('enables SYNC_INDICATOR when env var is "true"', async () => {
    process.env.NEXT_PUBLIC_SYNC_INDICATOR = 'true';

    const flags = await import('../../feature-flags');

    expect(flags.SYNC_INDICATOR).toBe(true);
  });

  it('enables OFFLINE_MODE when env var is "true"', async () => {
    process.env.NEXT_PUBLIC_OFFLINE_MODE = 'true';

    const flags = await import('../../feature-flags');

    expect(flags.OFFLINE_MODE).toBe(true);
  });
});
