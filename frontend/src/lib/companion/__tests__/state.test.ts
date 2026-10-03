/**
 * @vitest-environment node
 *
 * Pure-rules unit tests for the companion state machine (Phase 1). No DB, no
 * Next — just the deterministic egg → hatch-ready logic.
 */
import { describe, it, expect } from 'vitest';
import {
  EGG_VARIANTS,
  MASTERY_TARGET_CORRECT,
  buildCompetencyRing,
  competencyProgress,
  demonstratedCount,
  eggVariant,
  hatchProgress,
  isHatchReady,
  isValidEggVariant,
} from '../state';

describe('egg variants', () => {
  it('exposes four distinct variants with hex colours', () => {
    expect(EGG_VARIANTS).toHaveLength(4);
    const ids = EGG_VARIANTS.map((v) => v.id);
    expect(new Set(ids).size).toBe(4);
    for (const v of EGG_VARIANTS) expect(v.color).toMatch(/^#[0-9a-f]{6}$/i);
  });

  it('validates variant ids', () => {
    expect(isValidEggVariant('fox')).toBe(true);
    expect(isValidEggVariant('owl')).toBe(true);
    expect(isValidEggVariant('unicorn')).toBe(false);
    expect(isValidEggVariant('')).toBe(false);
    expect(isValidEggVariant(null)).toBe(false);
    expect(isValidEggVariant(42)).toBe(false);
  });

  it('looks up a variant and returns null for unknown/empty', () => {
    expect(eggVariant('fox')?.id).toBe('fox');
    expect(eggVariant('nope')).toBeNull();
    expect(eggVariant(null)).toBeNull();
    expect(eggVariant(undefined)).toBeNull();
  });
});

describe('competencyProgress', () => {
  it('reads zero progress when there is no mastery snapshot', () => {
    const p = competencyProgress('H_ROOK', undefined);
    expect(p).toEqual({
      code: 'H_ROOK',
      times_correct: 0,
      target: MASTERY_TARGET_CORRECT,
      progress: 0,
      demonstrated: false,
    });
  });

  it('is a fraction below target and not demonstrated', () => {
    const p = competencyProgress('H_ROOK', { competency_code: 'H_ROOK', times_correct: 1 });
    expect(p.progress).toBeCloseTo(1 / MASTERY_TARGET_CORRECT);
    expect(p.demonstrated).toBe(false);
  });

  it('is demonstrated at exactly the target and clamps above it', () => {
    const at = competencyProgress('H_ROOK', { competency_code: 'H_ROOK', times_correct: MASTERY_TARGET_CORRECT });
    expect(at.demonstrated).toBe(true);
    expect(at.progress).toBe(1);

    const over = competencyProgress('H_ROOK', { competency_code: 'H_ROOK', times_correct: 99 });
    expect(over.progress).toBe(1);
    expect(over.demonstrated).toBe(true);
  });

  it('floors fractional and ignores negative / non-finite counts', () => {
    expect(competencyProgress('X', { competency_code: 'X', times_correct: 2.9 }).times_correct).toBe(2);
    expect(competencyProgress('X', { competency_code: 'X', times_correct: -5 }).progress).toBe(0);
    expect(
      competencyProgress('X', { competency_code: 'X', times_correct: NaN }).progress,
    ).toBe(0);
  });
});

describe('buildCompetencyRing', () => {
  const codes = ['H_ROOK', 'H_BISHOP', 'H_QUEEN'];

  it('preserves code order and maps sparse mastery rows', () => {
    const ring = buildCompetencyRing(codes, [
      { competency_code: 'H_QUEEN', times_correct: 3 },
      { competency_code: 'H_ROOK', times_correct: 1 },
    ]);
    expect(ring.map((c) => c.code)).toEqual(codes);
    expect(ring[0].times_correct).toBe(1); // H_ROOK
    expect(ring[1].times_correct).toBe(0); // H_BISHOP — no row
    expect(ring[2].demonstrated).toBe(true); // H_QUEEN
  });
});

describe('hatch gate', () => {
  const codes = ['A', 'B', 'C'];

  it('counts demonstrated competencies', () => {
    const ring = buildCompetencyRing(codes, [
      { competency_code: 'A', times_correct: 3 },
      { competency_code: 'B', times_correct: 3 },
    ]);
    expect(demonstratedCount(ring)).toBe(2);
    expect(hatchProgress(ring)).toBeCloseTo(2 / 3);
  });

  it('is hatch-ready only when every competency is demonstrated', () => {
    const partial = buildCompetencyRing(codes, [
      { competency_code: 'A', times_correct: 3 },
      { competency_code: 'B', times_correct: 3 },
    ]);
    expect(isHatchReady(partial)).toBe(false);

    const full = buildCompetencyRing(codes, codes.map((c) => ({ competency_code: c, times_correct: 3 })));
    expect(isHatchReady(full)).toBe(true);
    expect(hatchProgress(full)).toBe(1);
  });

  it('an empty ring is never hatch-ready', () => {
    expect(isHatchReady([])).toBe(false);
    expect(hatchProgress([])).toBe(0);
  });

  it('an already-hatched companion is never hatch-ready again', () => {
    const full = buildCompetencyRing(codes, codes.map((c) => ({ competency_code: c, times_correct: 3 })));
    expect(isHatchReady(full, 'hatched')).toBe(false);
  });
});
