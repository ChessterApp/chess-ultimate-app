import { describe, it, expect } from 'vitest';
import { buildShareTitle, buildShareDescription } from '@/lib/gameShareMeta';

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
