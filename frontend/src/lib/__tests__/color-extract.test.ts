import { describe, it, expect } from 'vitest';
import { extractPalette } from '../color-extract';

// Build a RGBA pixel buffer from a list of {r,g,b,a,count} samples.
function makePixels(samples: Array<{ r: number; g: number; b: number; a?: number; count: number }>): Uint8Array {
  const total = samples.reduce((s, x) => s + x.count, 0);
  const out = new Uint8Array(total * 4);
  let i = 0;
  for (const s of samples) {
    for (let n = 0; n < s.count; n++) {
      out[i++] = s.r;
      out[i++] = s.g;
      out[i++] = s.b;
      out[i++] = s.a ?? 255;
    }
  }
  return out;
}

describe('extractPalette', () => {
  it('returns dominant for a saturated blue logo over white', () => {
    const pixels = makePixels([
      { r: 26, g: 115, b: 232, count: 200 }, // brand blue
      { r: 255, g: 255, b: 255, count: 300 }, // white background (filtered)
    ]);
    const p = extractPalette(pixels);
    expect(p.dominant.startsWith('#')).toBe(true);
    // Dominant should be close to the brand blue.
    const r = parseInt(p.dominant.slice(1, 3), 16);
    const g = parseInt(p.dominant.slice(3, 5), 16);
    const b = parseInt(p.dominant.slice(5, 7), 16);
    expect(b).toBeGreaterThan(r);
    expect(b).toBeGreaterThan(g);
  });

  it('picks a high-saturation accent when one exists', () => {
    const pixels = makePixels([
      { r: 60, g: 60, b: 60, count: 500 }, // dark gray (dominant)
      { r: 255, g: 200, b: 0, count: 100 }, // golden accent
    ]);
    const p = extractPalette(pixels);
    const r = parseInt(p.accent.slice(1, 3), 16);
    const g = parseInt(p.accent.slice(3, 5), 16);
    const b = parseInt(p.accent.slice(5, 7), 16);
    // Accent should be the saturated yellow, not the gray.
    expect(r).toBeGreaterThan(200);
    expect(b).toBeLessThan(100);
  });

  it('returns a sensible muted color when light grey exists', () => {
    const pixels = makePixels([
      { r: 200, g: 50, b: 50, count: 500 }, // saturated red dominant
      { r: 240, g: 240, b: 240, count: 200 }, // light grey muted candidate
    ]);
    const p = extractPalette(pixels);
    const r = parseInt(p.muted.slice(1, 3), 16);
    const g = parseInt(p.muted.slice(3, 5), 16);
    const b = parseInt(p.muted.slice(5, 7), 16);
    expect(Math.abs(r - g)).toBeLessThan(20);
    expect(Math.abs(g - b)).toBeLessThan(20);
  });

  it('filters near-transparent pixels', () => {
    const pixels = makePixels([
      { r: 50, g: 200, b: 50, count: 100, a: 0 },  // transparent green — should be filtered
      { r: 50, g: 50, b: 200, count: 50 },         // visible blue
    ]);
    const p = extractPalette(pixels);
    // Dominant should be the blue, not the (filtered) green.
    const r = parseInt(p.dominant.slice(1, 3), 16);
    const b = parseInt(p.dominant.slice(5, 7), 16);
    expect(b).toBeGreaterThan(r);
  });

  it('returns a safe fallback for an empty buffer', () => {
    const p = extractPalette(new Uint8Array(0));
    expect(p.dominant).toMatch(/^#[0-9a-f]{6}$/);
    expect(p.accent).toMatch(/^#[0-9a-f]{6}$/);
    expect(p.muted).toMatch(/^#[0-9a-f]{6}$/);
  });

  it('skips near-white and near-black pixels for dominant pick', () => {
    const pixels = makePixels([
      { r: 250, g: 250, b: 250, count: 1000 }, // near-white (filtered)
      { r: 5, g: 5, b: 5, count: 500 },        // near-black (filtered)
      { r: 200, g: 30, b: 30, count: 50 },     // visible red
    ]);
    const p = extractPalette(pixels);
    const r = parseInt(p.dominant.slice(1, 3), 16);
    expect(r).toBeGreaterThan(150);
  });
});
