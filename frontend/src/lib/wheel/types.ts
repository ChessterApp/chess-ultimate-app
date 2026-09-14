// Core types for the coach prize wheel (/games/wheel).

/** A single wedge on the wheel. `label` is coach-typed free text (any language). */
export interface WheelSegment {
  /** Stable client id for React keys / reordering. */
  id: string;
  /** Free text shown on the wedge — not translated. */
  label: string;
  /** CSS color of the wedge fill. */
  color: string;
  /** Optional emoji shown alongside the label. */
  emoji?: string;
}

/** A named, saveable wheel configuration. Mirrors the `wheel_presets` table. */
export interface WheelPreset {
  id: string;
  name: string;
  segments: WheelSegment[];
  createdBy?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}
