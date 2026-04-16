/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

// ─── Mocks ───────────────────────────────

// Feature flag — default to legacy mode
let mockLocalFirstSubscription = false;
vi.mock('@/lib/feature-flags', () => ({
  get LOCAL_FIRST_SUBSCRIPTION() { return mockLocalFirstSubscription; },
}));

const mockIsSignedIn = vi.fn().mockReturnValue(true);
const mockUserId = vi.fn().mockReturnValue('user-123');
vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({
    isSignedIn: mockIsSignedIn(),
    userId: mockUserId(),
  }),
}));

// Mock useQuery from @powersync/react
const mockQueryResult = vi.fn().mockReturnValue({
  data: undefined,
  isLoading: false,
  error: undefined,
});
vi.mock('@powersync/react', () => ({
  useQuery: () => mockQueryResult(),
}));

// Mock fetch for legacy mode
const mockFetchResponse = vi.fn();
global.fetch = vi.fn().mockImplementation(() =>
  Promise.resolve({
    json: () => Promise.resolve(mockFetchResponse()),
  })
) as any;

import { useSubscriptionFetch } from '../useSubscription';

// ─── Tests ───────────────────────────────

describe('useSubscription', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLocalFirstSubscription = false;
    mockIsSignedIn.mockReturnValue(true);
    mockUserId.mockReturnValue('user-123');
  });

  describe('legacy mode (feature flag off)', () => {
    it('should start in loading state', () => {
      mockFetchResponse.mockReturnValue({ active: true, plan: 'pro' });
      const { result } = renderHook(() => useSubscriptionFetch());
      expect(result.current.loading).toBe(true);
    });

    it('should fetch subscription status', async () => {
      mockFetchResponse.mockReturnValue({
        active: true,
        plan: 'pro',
        status: 'active',
        trialEnd: null,
      });

      const { result } = renderHook(() => useSubscriptionFetch());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.active).toBe(true);
      expect(result.current.plan).toBe('pro');
      expect(result.current.status).toBe('active');
    });

    it('should return inactive when not signed in', async () => {
      mockIsSignedIn.mockReturnValue(false);

      const { result } = renderHook(() => useSubscriptionFetch());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.active).toBe(false);
      expect(result.current.plan).toBeNull();
    });

    it('should handle fetch errors gracefully', async () => {
      (global.fetch as any).mockImplementationOnce(() => Promise.reject(new Error('Network error')));

      const { result } = renderHook(() => useSubscriptionFetch());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.active).toBe(false);
    });
  });

  describe('PowerSync mode (feature flag on)', () => {
    beforeEach(() => {
      mockLocalFirstSubscription = true;
    });

    it('should return loading when PowerSync not ready', () => {
      mockQueryResult.mockReturnValue({
        data: undefined,
        isLoading: true,
        error: undefined,
      });

      const { result } = renderHook(() => useSubscriptionFetch());
      expect(result.current.loading).toBe(true);
    });

    it('should return data from live query', () => {
      mockQueryResult.mockReturnValue({
        data: [{
          id: 'sub-1',
          active: 1,
          plan: 'pro',
          status: 'active',
          trial_end: null,
        }],
        isLoading: false,
        error: undefined,
      });

      const { result } = renderHook(() => useSubscriptionFetch());
      expect(result.current.loading).toBe(false);
      expect(result.current.active).toBe(true);
      expect(result.current.plan).toBe('pro');
      expect(result.current.status).toBe('active');
    });

    it('should return inactive when no subscription row exists', () => {
      mockQueryResult.mockReturnValue({
        data: [],
        isLoading: false,
        error: undefined,
      });

      const { result } = renderHook(() => useSubscriptionFetch());
      expect(result.current.loading).toBe(false);
      expect(result.current.active).toBe(false);
    });

    it('should return inactive when not signed in', () => {
      mockUserId.mockReturnValue(undefined);

      const { result } = renderHook(() => useSubscriptionFetch());
      expect(result.current.loading).toBe(false);
      expect(result.current.active).toBe(false);
    });
  });
});
