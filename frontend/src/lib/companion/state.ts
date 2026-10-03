/**
 * Companion — pure, framework-free state machine (Phase 1).
 *
 * The egg → hatch-ready progression, driven by competency evidence. Everything
 * here is deterministic and side-effect-free (no DB / Next imports) so it unit
 * tests without a database — mirroring economy.ts / companion-rules.ts. The
 * server-authoritative IO that feeds these functions lives in ./service.ts.
 *
 * Phase 1 does NOT hatch (that is the Phase 3 `hatch_companion` RPC); these
 * functions only surface whether the egg has met the hatch gate so the UI can
 * light up the ring. No coins, no gating — reading progress is always free.
 */

// ---------------------------------------------------------------------------
// Egg variants — the "choose your egg" options (persisted as companion.species)
// ---------------------------------------------------------------------------

export interface EggVariant {
  /** Stable id persisted in companion.species and used as the i18n key. */
  id: string;
  /** Egg shell colour (hex) for the static art + competency ring accent. */
  color: string;
}

/**
 * The four egg choices offered at onboarding. `id` doubles as the species the
 * egg hatches into (fox/owl/turtle/dragon) and as the i18n lookup key under the
 * `companion.eggs` namespace.
 */
export const EGG_VARIANTS: readonly EggVariant[] = [
  { id: 'fox', color: '#f97316' },
  { id: 'owl', color: '#8b5cf6' },
  { id: 'turtle', color: '#10b981' },
  { id: 'dragon', color: '#ef4444' },
] as const;

export function isValidEggVariant(id: unknown): id is string {
  return typeof id === 'string' && EGG_VARIANTS.some((v) => v.id === id);
}

/**
 * The species the slice hatches into when the egg was never explicitly chosen
 * (surprise mode). Only the fox is rigged in the vertical slice (one polished
 * animal, spec §1.6); a chosen egg keeps its own species at hatch.
 */
export const HATCH_SPECIES_DEFAULT = 'fox';

// ---------------------------------------------------------------------------
// Companion name — sanitized server-side at hatch (never trust raw client text)
// ---------------------------------------------------------------------------

/** Max visible length of a companion name (kid-friendly, DB `name` is TEXT). */
export const COMPANION_NAME_MAX = 24;

/**
 * Validate + sanitize a kid-entered companion name (Phase 3 hatch). Strips
 * control characters, collapses internal whitespace, trims the ends, and caps
 * the length. Returns the cleaned name, or `null` when nothing printable remains
 * (the route rejects that with 400). Pure + deterministic — unit-tested.
 */
export function sanitizeCompanionName(raw: unknown): string | null {
  if (typeof raw !== 'string') return null;
  const cleaned = raw.replace(/[\u0000-\u001f\u007f]/g, '').replace(/\s+/g, ' ').trim();
  if (cleaned.length === 0) return null;
  return cleaned.slice(0, COMPANION_NAME_MAX);
}

export function eggVariant(id: string | null | undefined): EggVariant | null {
  if (!id) return null;
  return EGG_VARIANTS.find((v) => v.id === id) ?? null;
}

// ---------------------------------------------------------------------------
// Competency progress — one ring segment per seeded competency
// ---------------------------------------------------------------------------

export type CompanionStage = 'egg' | 'hatched';

/**
 * Correct demonstrations needed for a competency to count as "demonstrated".
 * Deterministic constant (not economy config — this is a learning gate, not a
 * reward rate, so it never touches coins). Mirrors the first rungs of the SM-2
 * ladder ported in Phase 4.
 */
export const MASTERY_TARGET_CORRECT = 3;

/** The scheduler columns this phase reads from a mastery_state row. */
export interface MasterySnapshot {
  competency_code: string;
  times_correct: number;
}

export interface CompetencyProgress {
  code: string;
  times_correct: number;
  target: number;
  /** 0..1 fraction of the target met. */
  progress: number;
  demonstrated: boolean;
}

function clamp01(n: number): number {
  if (!Number.isFinite(n) || n <= 0) return 0;
  return n >= 1 ? 1 : n;
}

/** Progress for a single competency from its (optional) mastery snapshot. */
export function competencyProgress(
  code: string,
  mastery: MasterySnapshot | undefined,
): CompetencyProgress {
  const raw = mastery && Number.isFinite(mastery.times_correct) ? mastery.times_correct : 0;
  const correct = Math.max(0, Math.floor(raw));
  const target = MASTERY_TARGET_CORRECT;
  return {
    code,
    times_correct: correct,
    target,
    progress: clamp01(correct / target),
    demonstrated: correct >= target,
  };
}

/**
 * Build the competency ring: one progress segment per competency code, in the
 * order given. `mastery` is the owner's mastery_state rows (sparse — a missing
 * competency simply reads as zero progress).
 */
export function buildCompetencyRing(
  codes: string[],
  mastery: MasterySnapshot[],
): CompetencyProgress[] {
  const byCode = new Map<string, MasterySnapshot>();
  for (const m of mastery) byCode.set(m.competency_code, m);
  return codes.map((code) => competencyProgress(code, byCode.get(code)));
}

/** Count of demonstrated competencies in a ring. */
export function demonstratedCount(ring: CompetencyProgress[]): number {
  return ring.filter((c) => c.demonstrated).length;
}

/**
 * Fraction of the ring that is demonstrated (0..1). An empty ring is 0 — an egg
 * with no competencies to measure is never hatch-ready.
 */
export function hatchProgress(ring: CompetencyProgress[]): number {
  if (ring.length === 0) return 0;
  return demonstratedCount(ring) / ring.length;
}

/**
 * The hatch gate: the egg is ready to hatch once EVERY competency in the ring is
 * demonstrated (spec §4.2). An empty ring is never ready. A companion already
 * past the egg stage reports not-ready (there is nothing left to hatch).
 */
export function isHatchReady(ring: CompetencyProgress[], stage: CompanionStage = 'egg'): boolean {
  if (stage !== 'egg') return false;
  return ring.length > 0 && ring.every((c) => c.demonstrated);
}
