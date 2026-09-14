import { describe, it, expect } from 'vitest';
import {
  segmentAngle,
  segmentCenterAngle,
  polarToCartesian,
  wedgePath,
  winnerRotation,
  pointerSegmentIndex,
  segmentFontSize,
} from '../geometry';

describe('segmentAngle', () => {
  it('divides the circle evenly', () => {
    expect(segmentAngle(4)).toBe(90);
    expect(segmentAngle(6)).toBe(60);
    expect(segmentAngle(8)).toBe(45);
  });
  it('throws for non-positive counts', () => {
    expect(() => segmentAngle(0)).toThrow();
  });
});

describe('segmentCenterAngle', () => {
  it('returns the bisector of each segment', () => {
    expect(segmentCenterAngle(0, 4)).toBe(45);
    expect(segmentCenterAngle(1, 4)).toBe(135);
    expect(segmentCenterAngle(3, 4)).toBe(315);
  });
});

describe('polarToCartesian', () => {
  it('places angle 0 at the top of the circle', () => {
    const p = polarToCartesian(100, 100, 50, 0);
    expect(p.x).toBeCloseTo(100);
    expect(p.y).toBeCloseTo(50);
  });
  it('places angle 90 to the right (clockwise)', () => {
    const p = polarToCartesian(100, 100, 50, 90);
    expect(p.x).toBeCloseTo(150);
    expect(p.y).toBeCloseTo(100);
  });
  it('places angle 180 at the bottom', () => {
    const p = polarToCartesian(100, 100, 50, 180);
    expect(p.x).toBeCloseTo(100);
    expect(p.y).toBeCloseTo(150);
  });
});

describe('wedgePath', () => {
  it('produces a closed pie-slice path with an arc', () => {
    const d = wedgePath(100, 100, 50, 0, 90);
    expect(d).toMatch(/^M 100 100/);
    expect(d).toContain('A 50 50');
    expect(d.trim().endsWith('Z')).toBe(true);
  });
  it('sets the large-arc flag only for spans over 180 degrees', () => {
    expect(wedgePath(0, 0, 10, 0, 90)).toContain('A 10 10 0 0 1');
    expect(wedgePath(0, 0, 10, 0, 270)).toContain('A 10 10 0 1 1');
  });
});

describe('winnerRotation / pointerSegmentIndex round-trip', () => {
  it('lands the chosen segment exactly under the pointer for every count/index', () => {
    for (const count of [2, 3, 6, 8, 12, 17, 30]) {
      for (let i = 0; i < count; i++) {
        const rot = winnerRotation(i, count, 5);
        expect(pointerSegmentIndex(rot, count)).toBe(i);
      }
    }
  });
  it('includes the requested number of full spins', () => {
    const rot = winnerRotation(0, 4, 5);
    // 5 full turns = 1800deg, plus landing the segment.
    expect(rot).toBeGreaterThanOrEqual(1800);
    expect(rot).toBeLessThan(1800 + 360);
  });
  it('pointerSegmentIndex handles negative and large rotations', () => {
    expect(pointerSegmentIndex(-45, 4)).toBe(pointerSegmentIndex(315, 4));
    expect(pointerSegmentIndex(720 + 45, 4)).toBe(pointerSegmentIndex(45, 4));
  });
});

describe('segmentFontSize', () => {
  it('is largest for few segments and smallest for many', () => {
    expect(segmentFontSize(6)).toBe(20);
    expect(segmentFontSize(30)).toBe(9);
  });
  it('is monotonically non-increasing across the supported range', () => {
    let prev = Infinity;
    for (let n = 6; n <= 30; n++) {
      const size = segmentFontSize(n);
      expect(size).toBeLessThanOrEqual(prev);
      prev = size;
    }
  });
  it('clamps counts outside 6..30', () => {
    expect(segmentFontSize(2)).toBe(segmentFontSize(6));
    expect(segmentFontSize(100)).toBe(segmentFontSize(30));
  });
});
