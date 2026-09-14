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
export const DEFAULT_TIMEOUT_MS = 8000;
/** Below this many usable live puzzles we fall back to the bundled set. */
export const MIN_USABLE = 20;

export interface PrefetchOptions {
  level: TugLevel;
  themes: string[];
  count?: number;
  batchSize?: number;
  timeoutMs?: number;
  minUsable?: number;
  /** Injectable for tests; defaults to the global fetch. */
  fetchImpl?: typeof fetch;
  rng?: () => number;
  signal?: AbortSignal;
}

export interface PrefetchResult {
  queueA: TugPuzzle[];
  queueB: TugPuzzle[];
  /** True when the bundled fallback set was used instead of live puzzles. */
  usedFallback: boolean;
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

/**
 * The bundled fallback pool for a level/theme selection. Filters the hardcoded
 * set by rating band (and theme when that still leaves enough puzzles), but
 * never returns fewer than a playable minimum — an empty pool would stall the
 * game, which must never happen.
 */
export function fallbackPool(level: TugLevel, themes: string[]): TugPuzzle[] {
  const band = levelBand(level);
  const MIN_POOL = 8;
  let pool = TUG_PUZZLES.filter(
    (p) => p.rating >= band.ratingFrom && p.rating <= band.ratingTo,
  );
  if (themes.length > 0) {
    const themed = pool.filter((p) => p.themes.some((t) => themes.includes(t)));
    if (themed.length >= MIN_POOL) pool = themed;
  }
  if (pool.length < MIN_POOL) pool = TUG_PUZZLES;
  return pool;
}

async function fetchOne(
  url: string,
  fetchImpl: typeof fetch,
  signal: AbortSignal,
): Promise<PuzzleApiData | null> {
  try {
    const res = await fetchImpl(url, { signal });
    if (!res.ok) return null;
    const json = (await res.json()) as PuzzleApiResponse;
    if (!json?.success || !json.data) return null;
    return json.data;
  } catch {
    return null;
  }
}

/**
 * Prefetch a batch of live puzzles and split them into two disjoint team
 * queues, falling back to the bundled set on failure/timeout/too-few.
 */
export async function prefetchPuzzles(opts: PrefetchOptions): Promise<PrefetchResult> {
  const {
    level,
    themes,
    count = DEFAULT_PREFETCH_COUNT,
    batchSize = DEFAULT_BATCH_SIZE,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    minUsable = MIN_USABLE,
    fetchImpl = fetch,
    rng = Math.random,
    signal,
  } = opts;

  const url = buildPuzzleUrl(level, themes);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const onAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener('abort', onAbort);
  }

  const seen = new Set<string>();
  const usable: TugPuzzle[] = [];

  try {
    for (let i = 0; i < count && !controller.signal.aborted; i += batchSize) {
      const size = Math.min(batchSize, count - i);
      const batch = Array.from({ length: size }, () =>
        fetchOne(url, fetchImpl, controller.signal),
      );
      const results = await Promise.all(batch);
      for (const data of results) {
        const mapped = mapApiPuzzle(data);
        if (!mapped || seen.has(mapped.id)) continue;
        seen.add(mapped.id);
        usable.push(mapped);
      }
    }
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener('abort', onAbort);
  }

  if (usable.length >= minUsable) {
    return { ...splitQueues(usable, rng), usedFallback: false };
  }

  return {
    ...splitQueues(fallbackPool(level, themes), rng),
    usedFallback: true,
  };
}
