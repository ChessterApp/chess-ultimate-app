/**
 * The cached coach guard: an allowed member is looked up once a minute, a
 * restricted one on every call.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('server-only', () => ({}));
const requireApiAccessMock = vi.fn();
vi.mock('@/lib/require-api-access', () => ({
  requireApiAccess: () => requireApiAccessMock(),
}));

import { requireCoachAccess, resetCoachAccessCache } from '../coach-access';

beforeEach(() => {
  requireApiAccessMock.mockReset();
  resetCoachAccessCache();
  vi.useRealTimers();
});

describe('requireCoachAccess', () => {
  it('remembers an allowed member for a minute', async () => {
    vi.useFakeTimers();
    requireApiAccessMock.mockResolvedValue(null);
    expect(await requireCoachAccess('u1')).toBeNull();
    expect(await requireCoachAccess('u1')).toBeNull();
    expect(requireApiAccessMock).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(61_000);
    await requireCoachAccess('u1');
    expect(requireApiAccessMock).toHaveBeenCalledTimes(2);
  });

  it('never caches a denial', async () => {
    const denied = { status: 403 } as never;
    requireApiAccessMock.mockResolvedValue(denied);
    expect(await requireCoachAccess('u2')).toBe(denied);
    expect(await requireCoachAccess('u2')).toBe(denied);
    expect(requireApiAccessMock).toHaveBeenCalledTimes(2);
  });

  it('keeps users apart', async () => {
    requireApiAccessMock.mockResolvedValueOnce(null).mockResolvedValueOnce({ status: 403 });
    expect(await requireCoachAccess('a')).toBeNull();
    expect(await requireCoachAccess('b')).toEqual({ status: 403 });
  });
});
