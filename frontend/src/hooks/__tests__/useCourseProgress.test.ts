/**
 * @vitest-environment jsdom
 *
 * The Continue Learning card must never render stale numbers from a previous
 * successful fetch. So on ANY fetch failure the hook resets `courseProgress`
 * back to the empty map (mirroring useLessonCompletions), while still exposing
 * `error` and a `refetch` for the retry affordance.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

const apiFetchMock = vi.fn();

// Stable getToken identity so the hook's effect doesn't re-fire every render
// (real Clerk memoizes getToken).
vi.mock('@clerk/nextjs', () => {
  const getToken = async () => 'tok';
  return {
    useAuth: () => ({ getToken, isSignedIn: true, isLoaded: true }),
  };
});

vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
}));

import { useCourseProgress } from '../useCourseProgress';

beforeEach(() => {
  apiFetchMock.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('useCourseProgress', () => {
  it('exposes real progress on a successful fetch', async () => {
    const data = { c1: { courseId: 'c1', completedLessons: 3, totalLessons: 10, progress: 30 } };
    apiFetchMock.mockResolvedValueOnce(data);

    const { result } = renderHook(() => useCourseProgress());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.courseProgress).toEqual(data);
    expect(result.current.error).toBeNull();
  });

  it('resets courseProgress to empty when the fetch rejects', async () => {
    apiFetchMock.mockRejectedValueOnce(new Error('503 Service Unavailable'));

    const { result } = renderHook(() => useCourseProgress());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.courseProgress).toEqual({});
    expect(result.current.error).toBe('503 Service Unavailable');
  });

  it('clears stale progress when a later fetch fails, and refetch recovers', async () => {
    const good = { c1: { courseId: 'c1', completedLessons: 1, totalLessons: 37, progress: 3 } };
    // First load succeeds, retry fails, second retry succeeds again.
    apiFetchMock
      .mockResolvedValueOnce(good)
      .mockRejectedValueOnce(new Error('network error'))
      .mockResolvedValueOnce(good);

    const { result } = renderHook(() => useCourseProgress());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.courseProgress).toEqual(good);

    // Refetch → failure must wipe the stale snapshot, not retain it.
    act(() => result.current.refetch());
    await waitFor(() => expect(result.current.error).toBe('network error'));
    expect(result.current.courseProgress).toEqual({});

    // Refetch again → recovers real data and clears the error.
    act(() => result.current.refetch());
    await waitFor(() => expect(result.current.error).toBeNull());
    expect(result.current.courseProgress).toEqual(good);
  });
});
