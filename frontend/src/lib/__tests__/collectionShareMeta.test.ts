import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  sharedCollectionThumbnailUrl,
  fetchSharedCollectionMeta,
} from '@/lib/collectionShareMeta';

describe('sharedCollectionThumbnailUrl', () => {
  // NEXT_PUBLIC_BACKEND_URL is unset in the test env, so the public fallback
  // host must be used — never localhost, which crawlers can't reach.
  const BASE = 'https://api.chesster.io';

  it('builds the shared collection thumbnail URL and encodes the token', () => {
    expect(sharedCollectionThumbnailUrl('abc123')).toBe(
      `${BASE}/api/games/collection/shared/abc123/thumbnail.png`,
    );
    expect(sharedCollectionThumbnailUrl('a/b c')).toBe(
      `${BASE}/api/games/collection/shared/a%2Fb%20c/thumbnail.png`,
    );
  });

  it('uses the public backend host, not localhost', () => {
    expect(sharedCollectionThumbnailUrl('tok')).not.toContain('localhost');
  });
});

describe('fetchSharedCollectionMeta', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns the parsed meta on 200', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ owner_name: 'Alice', game_count: 12 }),
      })),
    );
    const meta = await fetchSharedCollectionMeta('tok');
    expect(meta).toEqual({ owner_name: 'Alice', game_count: 12 });
  });

  it('returns null on a non-ok response (revoked/unknown token)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, json: async () => ({}) })));
    expect(await fetchSharedCollectionMeta('gone')).toBeNull();
  });

  it('returns null when the fetch throws', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('network'); }));
    expect(await fetchSharedCollectionMeta('tok')).toBeNull();
  });
});
