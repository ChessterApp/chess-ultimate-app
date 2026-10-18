/**
 * Live puzzle packs for Tug of War.
 *
 * One request per match to the backend's `/api/puzzles/tug/pack` (real Lichess
 * puzzles from our own DB) deals both teams' queues; refills pass `exclude` so
 * a long match never repeats a puzzle. Puzzles arrive in the solving-position
 * format — `fen` has the solver to move and `moves` is the remaining line (the
 * opponent setup move is already applied server-side) — so they are used as-is.
 * Only when the backend is unreachable do we fall back to the bundled
 * `TUG_PUZZLES` set, so the game can ALWAYS start.
 */

import type { TugPuzzle } from './types';
import { TUG_PUZZLES } from './puzzles';
import { splitQueues } from './queues';

export type TugLevel = 'pawn' | 'knight' | 'rook' | 'queen';

/**
 * Setup-screen difficulty bands (the backend applies the same bands; here they
 * filter the offline set). Display labels live in i18n (`tugOfWar.levels.<id>`),
 * resolved in the SetupScreen.
 */
export const TUG_LEVELS: {
  id: TugLevel;
  ratingFrom: number;
  ratingTo: number;
}[] = [
  { id: 'pawn', ratingFrom: 400, ratingTo: 800 },
  { id: 'knight', ratingFrom: 800, ratingTo: 1200 },
  { id: 'rook', ratingFrom: 1200, ratingTo: 1600 },
  { id: 'queen', ratingFrom: 1600, ratingTo: 2400 },
];

/**
 * Curated theme choices offered on the setup screen. Display labels live in
 * i18n (`tugOfWar.themes.<tag>`), resolved in the SetupScreen.
 */
export const TUG_THEMES: { tag: string }[] = [
  { tag: 'mateIn1' },
  { tag: 'mateIn2' },
  { tag: 'fork' },
  { tag: 'pin' },
  { tag: 'skewer' },
  { tag: 'backRankMate' },
  { tag: 'discoveredAttack' },
  { tag: 'hangingPiece' },
];

export const PACK_URL = '/api/puzzles/tug/pack';
/** The match starts with this many puzzles per team (one pack of twice this). */
export const START_PER_TEAM = 30;
/** Puzzles per refill pack, split between the teams. */
export const REFILL_COUNT = 60;
export const DEFAULT_REQUEST_TIMEOUT_MS = 8000;

export interface PackRequest {
  level: TugLevel;
  themes: string[];
  count: number;
  /** Puzzle ids already dealt this match; the backend never returns them. */
  exclude?: string[];
  /** Abort timeout in ms. */
  timeoutMs?: number;
  /** Injectable for tests; defaults to the global fetch. */
  fetchImpl?: typeof fetch;
  signal?: AbortSignal;
}

export interface PrefetchOptions extends Omit<PackRequest, 'count' | 'exclude'> {
  rng?: () => number;
}

export interface PrefetchResult {
  queueA: TugPuzzle[];
  queueB: TugPuzzle[];
  /** True when the bundled fallback set was used instead of live puzzles. */
  usedFallback: boolean;
  /**
   * True when the offline fallback was used AND the selected theme(s) could not
   * be honored by the bundled set — a signal for an honest "themes unavailable"
   * notice rather than the generic offline badge.
   */
  themesUnavailable: boolean;
}

/** Look up a level's rating band, defaulting to the widest sensible range. */
function levelBand(level: TugLevel) {
  return TUG_LEVELS.find((l) => l.id === level) ?? TUG_LEVELS[0];
}

/** Build the pack query for a level + theme selection. */
export function buildPackUrl(
  level: TugLevel,
  themes: string[],
  count: number,
  exclude: string[] = [],
): string {
  const params = new URLSearchParams({ level, count: String(count) });
  if (themes.length > 0) params.append('themes', themes.join(','));
  if (exclude.length > 0) params.append('exclude', exclude.join(','));
  return `${PACK_URL}?${params.toString()}`;
}

/** Validate one pack puzzle; null when it lacks what the board needs. */
export function mapPackPuzzle(data: unknown): TugPuzzle | null {
  const p = data as Partial<TugPuzzle> | null;
  if (!p || typeof p.id !== 'string' || typeof p.fen !== 'string' || !Array.isArray(p.moves)) {
    return null;
  }
  const moves = p.moves.filter((m): m is string => typeof m === 'string' && m.length >= 4);
  if (!p.fen.trim() || moves.length === 0) return null;
  return {
    id: p.id,
    fen: p.fen.trim(),
    moves,
    rating: typeof p.rating === 'number' ? p.rating : 0,
    themes: Array.isArray(p.themes) ? p.themes : [],
  };
}

/**
 * Fetch one pack. Resolves to null when the backend is unreachable or errors
 * (the caller decides on the fallback); otherwise the usable puzzles, deduped
 * and never including an excluded id. An empty array means the filter ran dry.
 */
export async function fetchPack(req: PackRequest): Promise<TugPuzzle[] | null> {
  const {
    level,
    themes,
    count,
    exclude = [],
    timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
    fetchImpl = fetch,
    signal,
  } = req;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const onAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener('abort', onAbort);
  }
  try {
    const res = await fetchImpl(buildPackUrl(level, themes, count, exclude), {
      signal: controller.signal,
    });
    if (!res.ok) return null;
    const json = (await res.json()) as { puzzles?: unknown };
    if (!Array.isArray(json?.puzzles)) return null;
    const seen = new Set(exclude);
    const out: TugPuzzle[] = [];
    for (const raw of json.puzzles) {
      const p = mapPackPuzzle(raw);
      if (!p || seen.has(p.id)) continue;
      seen.add(p.id);
      out.push(p);
    }
    return out;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener('abort', onAbort);
  }
}

/**
 * Deal the match's opening queues from one live pack ({@link START_PER_TEAM}
 * per team). A pack thinner than that (a rare theme running dry) still plays
 * live; only an unreachable backend or a pack with less than one puzzle per
 * team falls back to the bundled offline set.
 */
export async function prefetchPuzzles(opts: PrefetchOptions): Promise<PrefetchResult> {
  const { level, themes, rng = Math.random } = opts;
  const puzzles = await fetchPack({ ...opts, count: START_PER_TEAM * 2 });
  if (puzzles && puzzles.length >= 2) {
    return { ...splitQueues(puzzles, rng), usedFallback: false, themesUnavailable: false };
  }
  const { pool, themesHonored } = fallbackPoolWithMeta(level, themes);
  return { ...splitQueues(pool, rng), usedFallback: true, themesUnavailable: !themesHonored };
}

/**
 * Fetch a refill pack ({@link REFILL_COUNT} puzzles, none of `exclude`) split
 * into two disjoint team deltas. Null when the backend failed; empty deltas
 * when the filter has run dry.
 */
export async function refillQueues(
  req: Omit<PackRequest, 'count'> & { rng?: () => number },
): Promise<{ queueA: TugPuzzle[]; queueB: TugPuzzle[] } | null> {
  const puzzles = await fetchPack({ ...req, count: REFILL_COUNT });
  return puzzles && splitQueues(puzzles, req.rng);
}

export interface FallbackPoolResult {
  pool: TugPuzzle[];
  /**
   * Whether the returned pool honors the requested theme(s). Vacuously true when
   * no theme was requested; false when a theme was requested but the bundled set
   * has none in this band (so we widened and the UI should say so).
   */
  themesHonored: boolean;
}

/**
 * The bundled fallback pool for a level/theme selection, plus an explicit signal
 * for whether the theme filter was actually honored (rather than silently
 * discarded). Filters the hardcoded set by rating band, then by theme; never
 * returns an empty pool — an empty pool would stall the game, which must never
 * happen.
 */
export function fallbackPoolWithMeta(level: TugLevel, themes: string[]): FallbackPoolResult {
  const band = levelBand(level);
  const MIN_POOL = 8;
  const bandPool = TUG_PUZZLES.filter(
    (p) => p.rating >= band.ratingFrom && p.rating <= band.ratingTo,
  );

  if (themes.length > 0) {
    const themed = bandPool.filter((p) => p.themes.some((t) => themes.includes(t)));
    if (themed.length > 0) {
      // Honor the theme even when the themed pool is thin: the queues cycle, so a
      // few real themed puzzles beat a full pool of the wrong shape.
      return { pool: themed, themesHonored: true };
    }
    // No themed puzzles in this band (e.g. a tactic theme at the Queen band):
    // widen to a varied playable pool and flag it so the UI can be honest.
    return { pool: bandPool.length >= MIN_POOL ? bandPool : TUG_PUZZLES, themesHonored: false };
  }

  // No theme filter: never trap players on a single puzzle shape. If the band
  // collapses to one difficulty tier or is too small, widen to the full set.
  let pool = bandPool;
  const distinctRatings = new Set(pool.map((p) => p.rating)).size;
  if (pool.length < MIN_POOL || distinctRatings < 2) pool = TUG_PUZZLES;
  return { pool, themesHonored: true };
}

/** Convenience wrapper returning only the pool (see {@link fallbackPoolWithMeta}). */
export function fallbackPool(level: TugLevel, themes: string[]): TugPuzzle[] {
  return fallbackPoolWithMeta(level, themes).pool;
}
