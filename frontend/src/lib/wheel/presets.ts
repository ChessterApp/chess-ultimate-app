// Preset (de)serialization, validation, and the built-in default wheel.

import type { WheelPreset, WheelSegment } from './types';

/** Palette used for the default wheel and when auto-coloring new segments. */
export const WHEEL_PALETTE = [
  '#c62828', // red
  '#f5efe0', // cream
  '#2e7d32', // green
  '#1565c0', // blue
  '#f9a825', // gold
  '#6a1b9a', // purple
  '#00838f', // teal
  '#d84315', // orange
] as const;

export const MIN_SEGMENTS = 2;
export const MAX_SEGMENTS = 30;

let idCounter = 0;
/** Small non-crypto id for client-side segment keys (order-stable, unique enough). */
export function makeSegmentId(): string {
  idCounter += 1;
  return `seg-${idCounter}-${idCounter.toString(36)}`;
}

/** Next palette color to use given how many segments already exist. */
export function nextColor(existingCount: number): string {
  return WHEEL_PALETTE[existingCount % WHEEL_PALETTE.length];
}

/** The single seeded default preset so first load is never empty. */
export function defaultPreset(): WheelPreset {
  const labels: Array<[string, string]> = [
    ['+1 ⭐', '#c62828'],
    ['Стикер', '#f5efe0'],
    ['Медаль', '#2e7d32'],
    ['Бонус', '#1565c0'],
    ['Спасибо!', '#f9a825'],
    ['Джекпот', '#6a1b9a'],
  ];
  return {
    id: 'default',
    name: 'Default',
    segments: labels.map(([label, color]) => ({
      id: makeSegmentId(),
      label,
      color,
    })),
  };
}

function isNonEmptyString(v: unknown): v is string {
  return typeof v === 'string' && v.length > 0;
}

/** Coerce arbitrary JSON into a valid segment, filling gaps with sane defaults. */
export function normalizeSegment(raw: unknown, index: number): WheelSegment {
  const obj = (raw ?? {}) as Record<string, unknown>;
  return {
    id: isNonEmptyString(obj.id) ? obj.id : makeSegmentId(),
    label: typeof obj.label === 'string' ? obj.label : '',
    color: isNonEmptyString(obj.color) ? obj.color : nextColor(index),
    emoji: isNonEmptyString(obj.emoji) ? obj.emoji : undefined,
  };
}

/** Parse a `segments` jsonb value (from Supabase or localStorage) into segments. */
export function deserializeSegments(raw: unknown): WheelSegment[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((s, i) => normalizeSegment(s, i));
}

/** Serialize segments for persistence (drops undefined emoji, strips volatile ids kept). */
export function serializeSegments(segments: WheelSegment[]): Array<Record<string, unknown>> {
  return segments.map((s) => {
    const out: Record<string, unknown> = { id: s.id, label: s.label, color: s.color };
    if (s.emoji) out.emoji = s.emoji;
    return out;
  });
}

/** Build a domain preset from a raw Supabase row. */
export function presetFromRow(row: {
  id: string;
  name: string;
  segments: unknown;
  created_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}): WheelPreset {
  return {
    id: row.id,
    name: row.name,
    segments: deserializeSegments(row.segments),
    createdBy: row.created_by ?? null,
    createdAt: row.created_at ?? null,
    updatedAt: row.updated_at ?? null,
  };
}

/** A preset is spinnable only with at least MIN_SEGMENTS wedges. */
export function isSpinnable(preset: WheelPreset | null | undefined): boolean {
  return !!preset && preset.segments.length >= MIN_SEGMENTS;
}
