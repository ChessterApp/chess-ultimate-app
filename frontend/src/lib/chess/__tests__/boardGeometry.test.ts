import { describe, it, expect } from 'vitest';
import { squareToPercent } from '../boardGeometry';

describe('squareToPercent', () => {
  describe('white orientation', () => {
    it('places a1 in the bottom-left corner', () => {
      expect(squareToPercent('a1', 'white')).toEqual({ left: 0, top: 87.5 });
    });
    it('places h8 in the top-right corner', () => {
      expect(squareToPercent('h8', 'white')).toEqual({ left: 87.5, top: 0 });
    });
    it('places g4 correctly', () => {
      // g=6th file → 6*12.5=75; rank4 → (8-4)*12.5=50
      expect(squareToPercent('g4', 'white')).toEqual({ left: 75, top: 50 });
    });
  });

  describe('black orientation (board rotated 180°)', () => {
    it('places a1 in the top-right corner', () => {
      expect(squareToPercent('a1', 'black')).toEqual({ left: 87.5, top: 0 });
    });
    it('places h8 in the bottom-left corner', () => {
      expect(squareToPercent('h8', 'black')).toEqual({ left: 0, top: 87.5 });
    });
    // Regression for the Lesson "Piece Value" puzzle #2 (Bg4+): the hint for g4
    // must land on the real g4 cell, not the 180°-mirror square (b5).
    it('places g4 on the flipped board (not b5)', () => {
      expect(squareToPercent('g4', 'black')).toEqual({ left: 12.5, top: 37.5 });
    });
    it('b5 and g4 are 180° mirrors of each other', () => {
      // This mirroring is exactly why the un-flipped renderer drew g4 on b5.
      expect(squareToPercent('g4', 'black')).toEqual(squareToPercent('b5', 'white'));
      expect(squareToPercent('b5', 'black')).toEqual(squareToPercent('g4', 'white'));
    });
  });
});
