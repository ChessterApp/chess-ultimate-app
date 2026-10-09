import { describe, it, expect, vi, afterEach } from 'vitest';
import { generateMetadata } from '../page';

/**
 * `/g/c/[token]` OG metadata generation. Mirrors the per-game `/g/u` OG tests:
 * resolves the collection → owner-and-count title + board thumbnail; falls back
 * to the generic Chesster card when the token is unknown/revoked.
 */

function paramsFor(token: string) {
  return { params: Promise.resolve({ token }) };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('generateMetadata for /g/c/[token]', () => {
  it('builds an owner-and-count title + board thumbnail when the token resolves', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ owner_name: 'Alice', game_count: 12 }),
      })),
    );

    const meta = await generateMetadata(paramsFor('tok123'));

    expect(meta.title).toContain('Alice');
    expect(meta.title).toContain('12');
    // Board thumbnail (absolute, public host) once the collection resolves.
    const ogImage = (meta.openGraph?.images as string[])[0];
    expect(ogImage).toBe(
      'https://api.chesster.io/api/games/collection/shared/tok123/thumbnail.png',
    );
    expect(meta.openGraph?.url).toBe('https://chesster.io/g/c/tok123');
  });

  it('falls back to the generic Chesster card for an unknown/revoked token', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, json: async () => ({}) })));

    const meta = await generateMetadata(paramsFor('gone'));

    expect(meta.title).toBe('Chess collection · Chesster');
    // Generic logo card — never the (404ing) board thumbnail.
    const ogImage = (meta.openGraph?.images as string[])[0];
    expect(ogImage).toBe('/static/images/chesster-logo-og.png');
  });
});
