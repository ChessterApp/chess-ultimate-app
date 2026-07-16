import { describe, it, expect, vi, beforeEach } from 'vitest';

// Capture the options handed to createClient so we can exercise the injected
// accessToken callback without hitting the network. Hoisted so it exists when
// the (hoisted) vi.mock factory runs.
const { createClientMock } = vi.hoisted(() => ({
  createClientMock: vi.fn((..._args: unknown[]) => ({ realtime: { setAuth: vi.fn() } })),
}));

vi.mock('@supabase/supabase-js', () => ({
  createClient: (...args: unknown[]) => createClientMock(...args),
}));

// Env must exist before the module (which reads it at import time) is loaded.
process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co';
process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key';

import { createClerkSupabaseClient, setRealtimeAuth } from '../supabase';

describe('createClerkSupabaseClient', () => {
  beforeEach(() => createClientMock.mockClear());

  it('wires an accessToken callback that forwards the Clerk token', async () => {
    createClerkSupabaseClient(async () => 'clerk-jwt');
    const opts = createClientMock.mock.calls.at(-1)?.[2] as unknown as {
      accessToken: () => Promise<string | null>;
    };
    expect(typeof opts.accessToken).toBe('function');
    await expect(opts.accessToken()).resolves.toBe('clerk-jwt');
  });

  it('coerces a null Clerk token to null (not undefined)', async () => {
    createClerkSupabaseClient(async () => null);
    const opts = createClientMock.mock.calls.at(-1)?.[2] as unknown as {
      accessToken: () => Promise<string | null>;
    };
    await expect(opts.accessToken()).resolves.toBeNull();
  });
});

describe('setRealtimeAuth', () => {
  it('pushes the fresh Clerk token onto the realtime socket', async () => {
    const setAuth = vi.fn();
    const client = { realtime: { setAuth } } as never;
    await setRealtimeAuth(client, async () => 'fresh-jwt');
    expect(setAuth).toHaveBeenCalledWith('fresh-jwt');
  });

  it('passes undefined when there is no token (clears socket auth)', async () => {
    const setAuth = vi.fn();
    const client = { realtime: { setAuth } } as never;
    await setRealtimeAuth(client, async () => null);
    expect(setAuth).toHaveBeenCalledWith(undefined);
  });
});
