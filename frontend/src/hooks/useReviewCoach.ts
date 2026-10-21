'use client';

import { useCallback, useRef, useState } from 'react';
import { useLocale } from 'next-intl';
import type { ReviewMove, ReviewResult, EngineEval } from '@/components/review/types';
import { marksFor, parseCoachMarkup, type CoachArrow } from '@/lib/coach/review-markup';

/**
 * Review Coach v1 (F1 per-move Explain + F3 whole-game recap).
 *
 * Builds grounded prompts from the engine truth the Review pipeline already
 * computed (FEN, SAN/UCI, classification, win%, best/second lines + evals) and
 * streams a Claude explanation through the existing coach SSE proxy
 * (`/api/coach/analysis/stream`). Every prompt embeds the exact 11-tier Review
 * taxonomy and a locale instruction so the coach narrates Review's own numbers
 * in the active language rather than inventing chess.
 *
 * Two-layer cache (REVIEW_COACH_PRD.md §6.4): an in-memory Map for same-session
 * instant repeats, then the persistent `review_coach_cache` table via
 * `/api/coach/review-cache`. Per-move key = fen+uci+locale (dedups across games
 * and users); summary key = pgn_hash+locale.
 */

/** Bump when the prompt wording changes — busts stale cached explanations. */
export const PROMPT_VERSION = 'v1';

/** The 11-tier Review taxonomy, best→worst, embedded verbatim in every prompt. */
export const CLASSIFICATION_LABELS =
  'brilliant · great · best · excellent · good · book · inaccuracy · mistake · miss · blunder · forced';

export type CoachStatus = 'idle' | 'streaming' | 'done' | 'error';

export interface CoachEntry {
  status: CoachStatus;
  /** Clean prose — inline [[arrows: …]] / [[squares: …]] marks removed. */
  content: string;
  error: string | null;
  /** Board shapes the explanation draws (from its marks / board_actions frames). */
  arrows: CoachArrow[];
  squares: string[];
}

const IDLE: CoachEntry = { status: 'idle', content: '', error: null, arrows: [], squares: [] };

/** Entry fields for a raw explanation (marks and all), as cached or streamed. */
function fromRaw(raw: string): Pick<CoachEntry, 'content' | 'arrows' | 'squares'> {
  const { text, arrows, squares } = parseCoachMarkup(raw);
  return { content: text, arrows, squares };
}

export interface OpeningInfo {
  name?: string;
  eco?: string;
  lastBookPly?: number;
}

// ── Pure helpers (unit-tested directly) ────────────────────────────────────

/** Per-move Explain cache key: prompt-version + fen + uci + locale. */
export function explainCacheKey(fen: string, uci: string, locale: string): string {
  return `${PROMPT_VERSION}:explain:${fen}|${uci}|${locale}`;
}

/** Whole-game summary cache key: prompt-version + pgn_hash + locale. */
export function summaryCacheKey(pgnHash: string, locale: string): string {
  return `${PROMPT_VERSION}:summary:${pgnHash}|${locale}`;
}

/**
 * Stable content hash of a game, derived from the UCI move sequence (a proxy
 * for a pgn_hash — the Review contract carries no PGN). FNV-1a, hex.
 */
export function pgnHash(moves: Pick<ReviewMove, 'uci'>[]): string {
  const seq = moves.map((m) => m.uci).join(' ');
  let h = 0x811c9dc5;
  for (let i = 0; i < seq.length; i++) {
    h ^= seq.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16).padStart(8, '0');
}

/** Human eval string from the engine contract: "+1.2", "−0.4", "#3", "#-2". */
export function formatEval(e: EngineEval | null | undefined): string {
  if (!e) return 'n/a';
  if (e.type === 'mate') return `#${e.value}`;
  const pawns = e.value / 100;
  const sign = pawns > 0 ? '+' : pawns < 0 ? '−' : '';
  return `${sign}${Math.abs(pawns).toFixed(1)}`;
}

const LOCALE_NAMES: Record<string, string> = {
  en: 'English',
  ru: 'Russian',
  kz: 'Kazakh',
};

function localeName(locale: string): string {
  return LOCALE_NAMES[locale] ?? locale;
}

/** "12." for a white ply, "12…" for a black ply. */
function moveNumberLabel(ply: number): string {
  const n = Math.floor((ply - 1) / 2) + 1;
  return ply % 2 === 1 ? `${n}.` : `${n}…`;
}

/**
 * F1 — the grounded per-move Explain prompt. Feeds the engine truth Review
 * already computed so the model narrates those facts; explicitly forbids
 * inventing a different best move.
 */
export function buildExplainQuery(
  move: ReviewMove,
  prev: ReviewMove | null,
  opening: OpeningInfo | undefined,
  locale: string,
): string {
  const mover = move.ply % 2 === 1 ? 'White' : 'Black';
  const isLastBook = !!opening && opening.lastBookPly === move.ply;
  const openingLine =
    opening?.name && (move.classification === 'book' || isLastBook)
      ? `Opening: ${opening.name}${opening.eco ? ` (${opening.eco})` : ''}${isLastBook ? ' — last book move' : ''}`
      : null;

  return `<review_move_explain>
<locale>Write the entire explanation in ${localeName(locale)} (${locale}).</locale>

<position>
FEN: ${move.fen}
Mover (just played this move): ${mover}
Move: ${moveNumberLabel(move.ply)} ${move.san} (${move.uci})
Phase: ${move.phase}
${openingLine ? openingLine + '\n' : ''}</position>

<engine_truth>
Review classified this move as: ${move.classification}
Win% for the mover after the move: ${move.winPercent.toFixed(1)}%
Eval after the move (White POV): ${formatEval(move.eval)}
Eval before the move (White POV): ${formatEval(prev ? prev.eval : { type: 'cp', value: 0 })}
Engine best move: ${move.best ? `${move.best.uci} (${formatEval(move.best.eval)})` : 'n/a'}
Engine second-best: ${move.second ? `${move.second.uci} (${formatEval(move.second.eval)})` : 'n/a'}
</engine_truth>

<taxonomy>
Review's 11 move-quality labels, best to worst: ${CLASSIFICATION_LABELS}.
Use ONLY this label ("${move.classification}") — do not translate it into another system.
</taxonomy>

<instructions>
You are a warm, concise chess coach for an improving player. In 2–4 short sentences, explain WHY ${move.san} earned the "${move.classification}" classification.
- Ground every claim in the engine_truth above. Do NOT invent a different best move or eval; if a stronger move existed, name the engine best move (${move.best ? move.best.uci : 'n/a'}).
- Speak plainly; avoid jargon dumps. No move-list dumps.
- Write in ${localeName(locale)}.
</instructions>
</review_move_explain>`;
}

/** Compact tally line "brilliant 1, blunder 2" — omits zero buckets. */
function tallyLine(counts: Record<string, number>): string {
  const parts = Object.entries(counts)
    .filter(([, n]) => n > 0)
    .map(([label, n]) => `${label} ${n}`);
  return parts.length ? parts.join(', ') : 'none';
}

function phaseLine(acc: Record<'w' | 'b', number | null>): string {
  const fmt = (v: number | null) => (v == null ? '—' : `${v.toFixed(1)}%`);
  return `White ${fmt(acc.w)} / Black ${fmt(acc.b)}`;
}

/** F3 — the whole-game recap prompt, grounded in the pipeline aggregates. */
export function buildRecapQuery(data: ReviewResult, locale: string): string {
  return `<game_recap>
<locale>Write the entire recap in ${localeName(locale)} (${locale}).</locale>

<opening>${data.opening?.name || 'Unknown'}${data.opening?.eco ? ` (${data.opening.eco})` : ''}</opening>

<estimated_rating>White ${data.estRating.w}, Black ${data.estRating.b}</estimated_rating>

<accuracy>
Overall: White ${data.accuracy.w.toFixed(1)}% / Black ${data.accuracy.b.toFixed(1)}%
Opening: ${phaseLine(data.phases.opening)}
Middlegame: ${phaseLine(data.phases.middlegame)}
Endgame: ${phaseLine(data.phases.endgame)}
</accuracy>

<move_quality_tally>
White: ${tallyLine(data.tally.w)}
Black: ${tallyLine(data.tally.b)}
</move_quality_tally>

<key_moment_plies>${data.keyMoments.length ? data.keyMoments.join(', ') : 'none'}</key_moment_plies>

<taxonomy>Review's 11 labels, best to worst: ${CLASSIFICATION_LABELS}.</taxonomy>

<instructions>
You are a chess coach recapping this whole game for the player. In 4–6 short sentences:
1. Name the biggest turning point(s), referencing the key-moment plies above.
2. Call out one recurring weakness, grounded in the tally and phase accuracy (e.g. "accuracy dropped most in the endgame").
3. Give ONE concrete thing to work on next.
Ground everything in the numbers above; do not invent moves or evals. Write in ${localeName(locale)}.
</instructions>
</game_recap>`;
}

// ── SSE streaming + persistent cache I/O ───────────────────────────────────

interface StreamResult {
  content: string;
  model: string | null;
}

/**
 * Consume the coach SSE proxy; resolve on {done}. `onUpdate` gets the raw
 * answer so far — the text plus the board_actions frames written back as
 * trailing marks, so one string carries both (and is what gets cached).
 */
async function streamCoach(
  body: { fen: string; query: string; context_type: string },
  onUpdate: (raw: string) => void,
  signal?: AbortSignal,
): Promise<StreamResult> {
  const response = await fetch('/api/coach/analysis/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok || !response.body) {
    let message = `Request failed (${response.status})`;
    try {
      const err = await response.json();
      message = err.error || message;
    } catch {
      /* non-JSON body */
    }
    throw new Error(message);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let text = '';
  let arrows: CoachArrow[] = [];
  let squares: string[] = [];
  let model: string | null = null;
  const raw = () => {
    const marks = marksFor(arrows, squares);
    return marks ? `${text} ${marks}` : text;
  };

  const consumeLine = (line: string) => {
    if (!line.startsWith('data: ')) return;
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(line.slice(6));
    } catch {
      return;
    }
    if (typeof data.delta === 'string') {
      text += data.delta;
      onUpdate(raw());
    }
    if (Array.isArray(data.board_actions)) {
      // Each action carries every arrow (highlight) of the answer so far.
      for (const action of data.board_actions as Array<Record<string, unknown>>) {
        if (action?.type === 'draw_arrows' && Array.isArray(action.arrows)) {
          arrows = (action.arrows as CoachArrow[]).filter((a) => a?.from && a?.to);
        } else if (action?.type === 'highlight_squares' && Array.isArray(action.squares)) {
          squares = (action.squares as unknown[]).filter((q): q is string => typeof q === 'string');
        }
      }
      onUpdate(raw());
    }
    if (typeof data.model === 'string') model = data.model;
    if (typeof data.error === 'string') throw new Error(data.error);
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) consumeLine(line);
  }
  if (buffer) consumeLine(buffer);

  return { content: raw(), model };
}

/** Read the persistent (Supabase) cache layer via the server route. */
async function readPersistentCache(key: string): Promise<string | null> {
  try {
    const res = await fetch(`/api/coach/review-cache?key=${encodeURIComponent(key)}`);
    if (!res.ok) return null;
    const data = await res.json();
    return typeof data.content === 'string' ? data.content : null;
  } catch {
    return null;
  }
}

/** Write-through to the persistent cache (best-effort; never blocks the UI). */
async function writePersistentCache(
  cache_key: string,
  kind: 'explain' | 'summary',
  locale: string,
  content: string,
  model: string | null,
): Promise<void> {
  try {
    await fetch('/api/coach/review-cache', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cache_key, kind, locale, content, model }),
    });
  } catch {
    /* cache write is best-effort */
  }
}

// ── Hook ───────────────────────────────────────────────────────────────────

export interface UseReviewCoach {
  /** Per-move Explain entries, keyed by explainCacheKey(fen, uci, locale). */
  explainByKey: Record<string, CoachEntry>;
  explainKeyFor: (move: ReviewMove) => string;
  explainMove: (move: ReviewMove, prev: ReviewMove | null, opening?: OpeningInfo) => Promise<void>;
  recap: CoachEntry;
  recapGame: (data: ReviewResult) => Promise<void>;
}

export function useReviewCoach(): UseReviewCoach {
  const locale = useLocale();
  const memRef = useRef<Map<string, string>>(new Map());
  const [explainByKey, setExplainByKey] = useState<Record<string, CoachEntry>>({});
  const [recap, setRecap] = useState<CoachEntry>(IDLE);

  const explainKeyFor = useCallback(
    (move: ReviewMove) => explainCacheKey(move.fen, move.uci, locale),
    [locale],
  );

  const setEntry = useCallback((key: string, patch: Partial<CoachEntry>) => {
    setExplainByKey((prev) => ({
      ...prev,
      [key]: { ...(prev[key] ?? IDLE), ...patch },
    }));
  }, []);

  const explainMove = useCallback(
    async (move: ReviewMove, prev: ReviewMove | null, opening?: OpeningInfo) => {
      const key = explainCacheKey(move.fen, move.uci, locale);

      // Layer 2 — client in-memory.
      const memHit = memRef.current.get(key);
      if (memHit != null) {
        setEntry(key, { status: 'done', error: null, ...fromRaw(memHit) });
        return;
      }

      setEntry(key, { status: 'streaming', error: null, ...fromRaw('') });

      try {
        // Layer 1 — persistent Supabase cache.
        const persisted = await readPersistentCache(key);
        if (persisted != null) {
          memRef.current.set(key, persisted);
          setEntry(key, { status: 'done', error: null, ...fromRaw(persisted) });
          return;
        }

        // Miss — stream from the LLM, appending tokens live.
        const query = buildExplainQuery(move, prev, opening, locale);
        const { content, model } = await streamCoach(
          { fen: move.fen, query, context_type: 'position' },
          (raw) => setEntry(key, fromRaw(raw)),
        );

        memRef.current.set(key, content);
        setEntry(key, { status: 'done', error: null, ...fromRaw(content) });
        void writePersistentCache(key, 'explain', locale, content, model);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Unknown error';
        setEntry(key, { status: 'error', error: message });
      }
    },
    [locale, setEntry],
  );

  const recapGame = useCallback(
    async (data: ReviewResult) => {
      const key = summaryCacheKey(pgnHash(data.moves), locale);

      const memHit = memRef.current.get(key);
      if (memHit != null) {
        setRecap({ ...IDLE, status: 'done', ...fromRaw(memHit) });
        return;
      }

      setRecap({ ...IDLE, status: 'streaming' });

      try {
        const persisted = await readPersistentCache(key);
        if (persisted != null) {
          memRef.current.set(key, persisted);
          setRecap({ ...IDLE, status: 'done', ...fromRaw(persisted) });
          return;
        }

        // The stream route requires a FEN; use the final position.
        const finalFen = data.moves.length
          ? data.moves[data.moves.length - 1].fen
          : 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
        const query = buildRecapQuery(data, locale);
        const { content, model } = await streamCoach(
          { fen: finalFen, query, context_type: 'game' },
          (raw) => setRecap((cur) => ({ ...cur, ...fromRaw(raw) })),
        );

        memRef.current.set(key, content);
        setRecap({ ...IDLE, status: 'done', ...fromRaw(content) });
        void writePersistentCache(key, 'summary', locale, content, model);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Unknown error';
        setRecap((cur) => ({ ...cur, status: 'error', error: message }));
      }
    },
    [locale],
  );

  return { explainByKey, explainKeyFor, explainMove, recap, recapGame };
}
