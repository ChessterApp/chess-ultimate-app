import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SupabasePowerSyncConnector } from '../connector';
import { createClerkSupabaseClient } from '@/lib/supabase';

// Mock supabase — the connector builds its write client via
// createClerkSupabaseClient(getToken), so return a mocked query builder there
// (from -> upsert / update.eq / delete.eq). Factory is hoisted, so keep the
// builder self-contained inside it.
vi.mock('@/lib/supabase', () => {
  const queryBuilder = {
    from: vi.fn(() => ({
      upsert: vi.fn().mockResolvedValue({ data: null, error: null }),
      update: vi.fn(() => ({
        eq: vi.fn().mockResolvedValue({ data: null, error: null }),
      })),
      delete: vi.fn(() => ({
        eq: vi.fn().mockResolvedValue({ data: null, error: null }),
      })),
    })),
  };
  return {
    supabase: queryBuilder,
    createClerkSupabaseClient: vi.fn(() => queryBuilder),
  };
});

describe('SupabasePowerSyncConnector', () => {
  const mockGetToken = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    process.env.NEXT_PUBLIC_POWERSYNC_URL = 'https://ps.example.com';
  });

  it('builds the write client with the connector getToken (authenticated writes)', () => {
    new SupabasePowerSyncConnector(mockGetToken);

    expect(createClerkSupabaseClient).toHaveBeenCalledWith(mockGetToken);
  });

  describe('fetchCredentials', () => {
    it('returns credentials with endpoint and token', async () => {
      mockGetToken.mockResolvedValue('jwt-token-123');
      const connector = new SupabasePowerSyncConnector(mockGetToken);

      const creds = await connector.fetchCredentials();

      expect(creds).toEqual({
        endpoint: 'https://ps.example.com',
        token: 'jwt-token-123',
      });
    });

    it('returns null when getToken returns null', async () => {
      mockGetToken.mockResolvedValue(null);
      const connector = new SupabasePowerSyncConnector(mockGetToken);

      const creds = await connector.fetchCredentials();

      expect(creds).toBeNull();
    });

    it('throws when NEXT_PUBLIC_POWERSYNC_URL is not set', async () => {
      delete process.env.NEXT_PUBLIC_POWERSYNC_URL;
      mockGetToken.mockResolvedValue('token');
      const connector = new SupabasePowerSyncConnector(mockGetToken);

      await expect(connector.fetchCredentials()).rejects.toThrow(
        'NEXT_PUBLIC_POWERSYNC_URL is not configured',
      );
    });
  });

  describe('uploadData', () => {
    it('completes transaction when no crud entries exist', async () => {
      const connector = new SupabasePowerSyncConnector(mockGetToken);
      const mockDb = {
        getNextCrudTransaction: vi.fn().mockResolvedValue(null),
      };

      await connector.uploadData(mockDb as any);

      expect(mockDb.getNextCrudTransaction).toHaveBeenCalledOnce();
    });

    it('processes crud entries and completes transaction', async () => {
      const connector = new SupabasePowerSyncConnector(mockGetToken);
      const completeFn = vi.fn();
      const mockTransaction = {
        crud: [
          { table: 'user_games', id: '1', op: 'PUT', opData: { white: 'Carlsen' } },
        ],
        complete: completeFn,
      };
      const mockDb = {
        getNextCrudTransaction: vi.fn().mockResolvedValue(mockTransaction),
      };

      await connector.uploadData(mockDb as any);

      expect(completeFn).toHaveBeenCalledOnce();
    });
  });
});
