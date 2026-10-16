import { describe, it, expect } from 'vitest';
import { toggleNag, sortNags, parseSanSuffix, suffixToNag, getNag, moveQualityNag } from '../nags';

describe('toggleNag', () => {
  it('adds a symbol', () => {
    expect(toggleNag(undefined, 1)).toEqual([1]);
  });

  it('replaces within the move and position groups', () => {
    expect(toggleNag([1], 4)).toEqual([4]);
    expect(toggleNag([1, 16], 18)).toEqual([1, 18]);
  });

  it('removes a symbol that is already present', () => {
    expect(toggleNag([3, 10], 3)).toEqual([10]);
  });

  it('allows multiple bonus symbols alongside one quality and one evaluation', () => {
    let nags = toggleNag([], 146);
    nags = toggleNag(nags, 36);
    nags = toggleNag(nags, 5);
    nags = toggleNag(nags, 13);
    expect(nags).toEqual([5, 13, 146, 36]);
  });

  it('treats Black-side variants as the same symbol', () => {
    expect(toggleNag([33], 32)).toEqual([]);
  });

  it('keeps unknown codes', () => {
    expect(toggleNag([250], 1)).toEqual([1, 250]);
  });
});

describe('sortNags', () => {
  it('orders move → position → other, unknown last', () => {
    expect(sortNags([999, 40, 14, 2])).toEqual([2, 14, 40, 999]);
  });
});

describe('suffix parsing', () => {
  it.each([
    ['e4!!', 'e4', 3], ['e4!', 'e4', 1], ['e4!?', 'e4', 5],
    ['Nf3?!', 'Nf3', 6], ['Nf3?', 'Nf3', 2], ['Qxf7+??', 'Qxf7+', 4],
  ])('%s', (token, san, nag) => {
    expect(parseSanSuffix(token)).toEqual({ san, nag });
  });

  it('leaves plain SAN alone', () => {
    expect(parseSanSuffix('O-O')).toEqual({ san: 'O-O', nag: null });
  });

  it('maps typed sequences', () => {
    expect(suffixToNag('!?')).toBe(5);
    expect(suffixToNag('!!!')).toBeNull();
  });
});

describe('lookup', () => {
  it('resolves Black-side codes to the shared symbol', () => {
    expect(getNag(37)?.symbol).toBe('↑');
    expect(getNag(250)).toBeUndefined();
  });

  it('finds the move-quality symbol', () => {
    expect(moveQualityNag([16, 7])?.symbol).toBe('□');
    expect(moveQualityNag([16])).toBeUndefined();
  });
});
