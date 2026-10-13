import { describe, it, expect } from 'vitest';
import { squareToPercent } from '../board-geometry';

describe('squareToPercent', () => {
  it('white at the bottom: a1 bottom-left, h8 top-right', () => {
    expect(squareToPercent('a1', 'white')).toEqual({ left: 0, top: 87.5 });
    expect(squareToPercent('h8', 'white')).toEqual({ left: 87.5, top: 0 });
    expect(squareToPercent('e4', 'white')).toEqual({ left: 50, top: 50 });
  });

  it('black at the bottom: mirrored on both axes', () => {
    expect(squareToPercent('a1', 'black')).toEqual({ left: 87.5, top: 0 });
    expect(squareToPercent('h8', 'black')).toEqual({ left: 0, top: 87.5 });
    expect(squareToPercent('e4', 'black')).toEqual({ left: 37.5, top: 37.5 });
  });

  it('rejects what is not a square', () => {
    expect(squareToPercent('i1', 'white')).toBeNull();
    expect(squareToPercent('a9', 'white')).toBeNull();
    expect(squareToPercent('', 'black')).toBeNull();
  });
});
