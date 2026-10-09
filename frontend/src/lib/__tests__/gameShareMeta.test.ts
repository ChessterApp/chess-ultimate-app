import { describe, it, expect } from 'vitest';
import {
  buildShareTitle,
  buildShareDescription,
  masterThumbnailUrl,
  sharedThumbnailUrl,
} from '@/lib/gameShareMeta';

const WATCH = 'Watch and analyze this game on Chesster';

describe('buildShareTitle', () => {
  it('formats "{white} vs {black} · {result}"', () => {
    expect(
      buildShareTitle({ white: 'Carlsen', black: 'Nakamura', result: '1-0' }),
    ).toBe('Carlsen vs Nakamura · 1-0');
  });

  it('omits the result segment when absent', () => {
    expect(buildShareTitle({ white: 'Carlsen', black: 'Nakamura' })).toBe(
      'Carlsen vs Nakamura',
    );
  });

  it('returns null when a player name is missing (caller falls back)', () => {
    expect(buildShareTitle({ white: 'Carlsen', result: '1-0' })).toBeNull();
    expect(buildShareTitle(null)).toBeNull();
    expect(buildShareTitle(undefined)).toBeNull();
  });
});

describe('buildShareDescription', () => {
  it('joins event · date · watch suffix', () => {
    expect(
      buildShareDescription(
        { event: 'Sinquefield Cup', date: '2024.08.24' },
        WATCH,
      ),
    ).toBe(`Sinquefield Cup · 2024.08.24 · ${WATCH}`);
  });

  it('drops missing leading segments', () => {
    expect(buildShareDescription({ event: 'Tata Steel' }, WATCH)).toBe(
      `Tata Steel · ${WATCH}`,
    );
    expect(buildShareDescription(null, WATCH)).toBe(WATCH);
  });

  it('treats PGN placeholder dates as empty', () => {
    expect(
      buildShareDescription({ event: 'Tata Steel', date: '????.??.??' }, WATCH),
    ).toBe(`Tata Steel · ${WATCH}`);
  });
});

describe('thumbnail URLs', () => {
  // NEXT_PUBLIC_BACKEND_URL is unset in the test env, so the public fallback
  // host must be used — never localhost, which crawlers can't reach.
  const BASE = 'https://api.chesster.io';

  it('builds the master board-thumbnail URL with source', () => {
    expect(masterThumbnailUrl('twic', 42)).toBe(
      `${BASE}/api/openings/games/42/thumbnail.png?source=twic`,
    );
    expect(masterThumbnailUrl('lichess', 7)).toBe(
      `${BASE}/api/openings/games/7/thumbnail.png?source=lichess`,
    );
  });

  it('builds the shared user-game thumbnail URL and encodes the token', () => {
    expect(sharedThumbnailUrl('abc123')).toBe(
      `${BASE}/api/games/shared/abc123/thumbnail.png`,
    );
    expect(sharedThumbnailUrl('a/b c')).toBe(
      `${BASE}/api/games/shared/a%2Fb%20c/thumbnail.png`,
    );
  });

  it('uses the public backend host, not localhost', () => {
    expect(masterThumbnailUrl('twic', 1)).not.toContain('localhost');
    expect(sharedThumbnailUrl('tok')).not.toContain('localhost');
  });
});
