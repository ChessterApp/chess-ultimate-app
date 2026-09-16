/**
 * Live puzzle prefetch for Tug of War.
 *
 * At match setup we pull a batch of fresh puzzles from the app's existing
 * `/api/puzzle` route (one random puzzle per call) and split them into two
 * disjoint team queues. If the network is slow, fails, or returns too few
 * usable puzzles we fall back to the bundled `TUG_PUZZLES` set so the game can
 * ALWAYS start.
 *
 * Mapping convention (mirrors src/app/puzzle/page.tsx exactly): the API's `FEN`
 * field is already the position AFTER the opponent's `preMove`, i.e. the
 * position where the SOLVING side moves, and `moves` is the solution line from
 * that turn onward. We therefore use `FEN`/`moves` directly and never apply
 * `preMove`/`previousFEN`.
 */

import type { TugPuzzle } from './types';
import { TUG_PUZZLES } from './puzzles';
import { splitQueues } from './queues';

/** Raw puzzle shape returned by GET /api/puzzle. */
export interface PuzzleApiData {
  lichessId: string;
  previousFEN: string;
  FEN: string;
  moves: string;
  preMove: string;
  rating: number;
  themes: string[];
  gameURL: string;
}

interface PuzzleApiResponse {
  success: boolean;
  data?: PuzzleApiData;
  error?: string;
}

export type TugLevel = 'pawn' | 'knight' | 'rook' | 'queen';

/**
 * Setup-screen difficulty bands → `ratingFrom`/`ratingTo` API params. Display
 * labels live in i18n (`tugOfWar.levels.<id>`), resolved in the SetupScreen.
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

export const DEFAULT_PREFETCH_COUNT = 60;
export const DEFAULT_BATCH_SIZE = 8;
/** Per-request timeout. One slow request no longer sinks the whole prefetch. */
export const DEFAULT_REQUEST_TIMEOUT_MS = 4000;
/**
 * Once this many usable live puzzles have arrived we start the match and keep
 * fetching the rest in the background. Small on purpose: the queues cycle, so
 * the match can begin thin and top up as it runs.
 */
export const DEFAULT_MIN_USABLE = 8;

export interface PrefetchOptions {
  level: TugLevel;
  themes: string[];
  count?: number;
  batchSize?: number;
  /** Per-request abort timeout in ms. */
  requestTimeoutMs?: number;
  /** Usable puzzles needed before the match starts (and the rest stream in). */
  minUsable?: number;
  /** Injectable for tests; defaults to the global fetch. */
  fetchImpl?: typeof fetch;
  rng?: () => number;
  signal?: AbortSignal;
  /**
   * Invoked (live path only) with additional queue puzzles fetched AFTER the
   * early start, so the caller can top up each team's queue while the match
   * runs. The two arrays are disjoint from each other and from the initial
   * queues.
   */
  onTopUp?: (deltaA: TugPuzzle[], deltaB: TugPuzzle[]) => void;
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

/** Build the `/api/puzzle` query for a level + theme selection. */
export function buildPuzzleUrl(level: TugLevel, themes: string[]): string {
  const band = levelBand(level);
  const params = new URLSearchParams();
  if (themes.length > 0) params.append('themes', themes.join(','));
  params.append('ratingFrom', String(band.ratingFrom));
  params.append('ratingTo', String(band.ratingTo));
  return `/api/puzzle?${params.toString()}`;
}

/**
 * Map one API puzzle to the internal {@link TugPuzzle}. Returns null when the
 * payload is missing the fields the board needs.
 */
export function mapApiPuzzle(data: PuzzleApiData | undefined | null): TugPuzzle | null {
  if (!data || typeof data.FEN !== 'string' || typeof data.moves !== 'string') {
    return null;
  }
  const fen = data.FEN.trim();
  const moves = data.moves.trim().split(/\s+/).filter(Boolean);
  if (!fen || moves.length === 0) return null;
  return {
    id: data.lichessId || `${fen}|${moves.join('')}`,
    fen,
    moves,
    rating: typeof data.rating === 'number' ? data.rating : 0,
    themes: Array.isArray(data.themes) ? data.themes : [],
  };
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

/**
 * Fetch a single puzzle with its own abort timeout. A per-request timeout means
 * one slow request costs at most `timeoutMs` instead of eating the whole
 * prefetch budget. The outer `signal` (e.g. component unmount) aborts too.
 */
async function fetchOne(
  url: string,
  fetchImpl: typeof fetch,
  timeoutMs: number,
  outerSignal?: AbortSignal,
): Promise<PuzzleApiData | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const onAbort = () => controller.abort();
  if (outerSignal) {
    if (outerSignal.aborted) controller.abort();
    else outerSignal.addEventListener('abort', onAbort);
  }
  try {
    const res = await fetchImpl(url, { signal: controller.signal });
    if (!res.ok) return null;
    const json = (await res.json()) as PuzzleApiResponse;
    if (!json?.success || !json.data) return null;
    return json.data;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
    if (outerSignal) outerSignal.removeEventListener('abort', onAbort);
  }
}

/**
 * Prefetch live puzzles and split them into two disjoint team queues.
 *
 * Robust by design: each request has its own timeout; the match starts as soon
 * as `minUsable` puzzles arrive (the rest stream in via `onTopUp`); and it only
 * falls back to the bundled offline set on a genuine failure — the first batch
 * returning nothing usable, or not even `minUsable` puzzles across the whole
 * pass — not merely because the full count did not arrive in time.
 */
export function prefetchPuzzles(opts: PrefetchOptions): Promise<PrefetchResult> {
  const {
    level,
    themes,
    count = DEFAULT_PREFETCH_COUNT,
    batchSize = DEFAULT_BATCH_SIZE,
    requestTimeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
    minUsable = DEFAULT_MIN_USABLE,
    fetchImpl = fetch,
    rng = Math.random,
    signal,
    onTopUp,
  } = opts;

  const url = buildPuzzleUrl(level, themes);

  const fallbackResult = (): PrefetchResult => {
    const { pool, themesHonored } = fallbackPoolWithMeta(level, themes);
    return { ...splitQueues(pool, rng), usedFallback: true, themesUnavailable: !themesHonored };
  };

  return new Promise<PrefetchResult>((resolve) => {
    const seen = new Set<string>();
    const usable: TugPuzzle[] = [];
    let started = false; // early-start already fired
    let dealt = 0; // puzzles delivered so far (initial queues + top-ups)

    const settleLive = () => {
      started = true;
      dealt = usable.length;
      resolve({ ...splitQueues(usable.slice(), rng), usedFallback: false, themesUnavailable: false });
    };

    const flushTopUp = () => {
      if (!onTopUp || usable.length <= dealt) return;
      const fresh = usable.slice(dealt);
      dealt = usable.length;
      const { queueA, queueB } = splitQueues(fresh, rng);
      onTopUp(queueA, queueB);
    };

    const run = async () => {
      for (let i = 0; i < count; i += batchSize) {
        if (signal?.aborted) break;
        const size = Math.min(batchSize, count - i);
        const results = await Promise.all(
          Array.from({ length: size }, () => fetchOne(url, fetchImpl, requestTimeoutMs, signal)),
        );
        for (const data of results) {
          const mapped = mapApiPuzzle(data);
          if (!mapped || seen.has(mapped.id)) continue;
          seen.add(mapped.id);
          usable.push(mapped);
        }
        // Genuine failure: the very first batch produced nothing usable → the
        // API is down/blocked, so fall back immediately instead of retrying 60×.
        if (!started && i === 0 && usable.length === 0) {
          resolve(fallbackResult());
          return;
        }
        if (!started) {
          if (usable.length >= minUsable) settleLive();
        } else {
          flushTopUp();
        }
      }
      // Loop finished without an early start. Either enough trickled in to play
      // (slow-but-working API), or too few ever arrived → offline.
      if (!started) {
        if (usable.length >= minUsable) settleLive();
        else resolve(fallbackResult());
      }
    };

    run().catch(() => {
      if (!started) resolve(fallbackResult());
    });
  });
}
