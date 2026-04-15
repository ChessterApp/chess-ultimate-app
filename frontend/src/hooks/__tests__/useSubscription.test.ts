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

// Mock PowerSync context
const mockCollections = {
  subscriptions: { id: 'subscriptions-collection' },
};
const mockPowerSyncContext = vi.fn().mockReturnValue({
  database: null,
  collections: null,
  isReady: false,
});
vi.mock('@/lib/powersync/PowerSyncProvider', () => ({
  usePowerSyncContext: () => mockPowerSyncContext(),
}));

// Mock useLiveQuery
const mockLiveQueryResult = vi.fn().mockReturnValue({
  data: undefined,
  isLoading: false,
  isReady: true,
});
vi.mock('@tanstack/react-db', () => ({
  useLiveQuery: () => mockLiveQueryResult(),
}));

vi.mock('@tanstack/db', () => ({
  eq: vi.fn(),
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
    mockPowerSyncContext.mockReturnValue({
      database: null,
      collections: null,
      isReady: false,
    });
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
      mockPowerSyncContext.mockReturnValue({
        database: {},
        collections: mockCollections,
        isReady: false,
      });
      mockLiveQueryResult.mockReturnValue({
        data: undefined,
        isLoading: true,
        isReady: false,
      });

      const { result } = renderHook(() => useSubscriptionFetch());
      expect(result.current.loading).toBe(true);
    });

    it('should return data from live query', () => {
      mockPowerSyncContext.mockReturnValue({
        database: {},
        collections: mockCollections,
        isReady: true,
      });
      mockLiveQueryResult.mockReturnValue({
        data: [{
          id: 'sub-1',
          active: 1,
          plan: 'pro',
          status: 'active',
          trial_end: null,
        }],
        isLoading: false,
        isReady: true,
      });

      const { result } = renderHook(() => useSubscriptionFetch());
      expect(result.current.loading).toBe(false);
      expect(result.current.active).toBe(true);
      expect(result.current.plan).toBe('pro');
      expect(result.current.status).toBe('active');
    });

    it('should return inactive when no subscription row exists', () => {
      mockPowerSyncContext.mockReturnValue({
        database: {},
        collections: mockCollections,
        isReady: true,
      });
      mockLiveQueryResult.mockReturnValue({
        data: [],
        isLoading: false,
        isReady: true,
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
