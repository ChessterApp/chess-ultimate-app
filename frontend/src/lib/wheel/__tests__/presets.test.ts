import { describe, it, expect } from 'vitest';
import {
  defaultPreset,
  deserializeSegments,
  serializeSegments,
  normalizeSegment,
  presetFromRow,
  isSpinnable,
  nextColor,
  WHEEL_PALETTE,
  MIN_SEGMENTS,
} from '../presets';

describe('defaultPreset', () => {
  it('is non-empty and spinnable', () => {
    const p = defaultPreset();
    expect(p.segments.length).toBeGreaterThanOrEqual(MIN_SEGMENTS);
    expect(isSpinnable(p)).toBe(true);
  });
  it('gives every segment a unique id', () => {
    const ids = defaultPreset().segments.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
  it('has exactly 20 tiles', () => {
    expect(defaultPreset().segments).toHaveLength(20);
  });
  it('uses short labels that will not overflow the disc', () => {
    // The mobile-overflow fix replaced long Russian labels with short tokens;
    // keep them short so rotating text stays inside the wheel.
    for (const s of defaultPreset().segments) {
      expect(s.label.length).toBeLessThanOrEqual(3);
    }
  });
  it('renders multipliers as plain text with no emoji', () => {
    const multipliers = defaultPreset().segments.filter((s) => /^\d+X$/.test(s.label));
    expect(multipliers.length).toBeGreaterThan(0);
    for (const s of multipliers) {
      expect(s.emoji).toBe('');
    }
  });
});

describe('nextColor', () => {
  it('cycles through the palette', () => {
    expect(nextColor(0)).toBe(WHEEL_PALETTE[0]);
    expect(nextColor(WHEEL_PALETTE.length)).toBe(WHEEL_PALETTE[0]);
  });
});

describe('normalizeSegment', () => {
  it('fills missing fields with defaults', () => {
    const seg = normalizeSegment({}, 0);
    expect(seg.label).toBe('');
    expect(seg.color).toBe(nextColor(0));
    expect(seg.id).toMatch(/^seg-/);
    expect(seg.emoji).toBeUndefined();
  });
  it('preserves valid fields', () => {
    const seg = normalizeSegment({ id: 'x', label: 'Приз', color: '#123456', emoji: '🎁' }, 2);
    expect(seg).toEqual({ id: 'x', label: 'Приз', color: '#123456', emoji: '🎁', description: undefined });
  });
  it('reads a description string, otherwise undefined', () => {
    expect(normalizeSegment({ description: 'You won a coffee!' }, 0).description).toBe('You won a coffee!');
    expect(normalizeSegment({ description: '' }, 0).description).toBeUndefined();
    expect(normalizeSegment({ description: 42 }, 0).description).toBeUndefined();
    expect(normalizeSegment({}, 0).description).toBeUndefined();
  });
});

describe('serialize / deserialize round-trip', () => {
  it('preserves segment data', () => {
    const original = defaultPreset().segments;
    const round = deserializeSegments(serializeSegments(original));
    // Empty-string emoji is falsy, so it is dropped on serialize and comes back
    // as undefined — equivalent to "no emoji". Normalize before comparing.
    const normalized = original.map((s) => ({ ...s, emoji: s.emoji || undefined }));
    expect(round).toEqual(normalized);
  });
  it('drops empty emoji on serialize', () => {
    const [s] = serializeSegments([{ id: 'a', label: 'L', color: '#fff' }]);
    expect('emoji' in s).toBe(false);
  });
  it('round-trips a description when set', () => {
    const original = [{ id: 'a', label: 'L', color: '#fff', description: 'Custom win text' }];
    const round = deserializeSegments(serializeSegments(original));
    expect(round[0].description).toBe('Custom win text');
  });
  it('drops an empty/undefined description on serialize', () => {
    const [s] = serializeSegments([{ id: 'a', label: 'L', color: '#fff' }]);
    expect('description' in s).toBe(false);
    const round = deserializeSegments(serializeSegments([{ id: 'a', label: 'L', color: '#fff' }]));
    expect(round[0].description).toBeUndefined();
  });
  it('deserialize tolerates garbage input', () => {
    expect(deserializeSegments(null)).toEqual([]);
    expect(deserializeSegments('nope')).toEqual([]);
    expect(deserializeSegments([{}, 42]).length).toBe(2);
  });
});

describe('presetFromRow', () => {
  it('maps a Supabase row into a domain preset', () => {
    const p = presetFromRow({
      id: 'uuid-1',
      name: 'младшая группа',
      segments: [{ id: 'a', label: 'A', color: '#c62828' }],
      created_by: 'user_123',
      created_at: '2026-09-14T00:00:00Z',
      updated_at: '2026-09-14T00:00:00Z',
    });
    expect(p.id).toBe('uuid-1');
    expect(p.name).toBe('младшая группа');
    expect(p.segments).toHaveLength(1);
    expect(p.createdBy).toBe('user_123');
  });
});

describe('isSpinnable', () => {
  it('requires at least MIN_SEGMENTS', () => {
    expect(isSpinnable(null)).toBe(false);
    expect(isSpinnable({ id: 'x', name: 'x', segments: [] })).toBe(false);
    expect(isSpinnable(defaultPreset())).toBe(true);
  });
});
