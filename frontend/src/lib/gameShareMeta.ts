/**
 * gameShareMeta — server-side helpers for the `/g/<slug>` short-link OG cards.
 *
 * Pure builders (title/description/date cleanup) are split out from the network
 * fetch so they can be unit-tested without a running backend. The fetch hits the
 * PUBLIC `/api/openings/games/<id>/meta` endpoint — header fields only, never PGN.
 */
import type { GameSource } from './gameSlug';

export interface GameMeta {
  white?: string | null;
  black?: string | null;
  result?: string | null;
  event?: string | null;
  date?: string | null;
  white_elo?: number | null;
  black_elo?: number | null;
}

/** PGN "unknown" date fields (e.g. `????.??.??`) should not surface in previews. */
function cleanDate(date?: string | null): string {
  if (!date) return '';
  const trimmed = date.trim();
  if (!trimmed || trimmed.includes('?')) return '';
  return trimmed;
}

/**
 * OG/Twitter card title: `"{white} vs {black} · {result}"`.
 * Returns null when player names are missing so the caller can fall back to a
 * generic title.
 */
export function buildShareTitle(meta: GameMeta | null | undefined): string | null {
  if (!meta || !meta.white || !meta.black) return null;
  const base = `${meta.white} vs ${meta.black}`;
  return meta.result ? `${base} · ${meta.result}` : base;
}

/**
 * OG/Twitter card description: `"{event} · {date} · {watchSuffix}"`, dropping
 * any empty leading segments. `watchSuffix` is the i18n "Watch and analyze…" line.
 */
export function buildShareDescription(
  meta: GameMeta | null | undefined,
  watchSuffix: string,
): string {
  const parts: string[] = [];
  if (meta?.event) parts.push(meta.event);
  const date = cleanDate(meta?.date);
  if (date) parts.push(date);
  parts.push(watchSuffix);
  return parts.join(' · ');
}

/**
 * Fetch public game metadata from the Flask backend. Never throws — returns
 * null on any network/HTTP error so `generateMetadata` can fall back cleanly.
 */
export async function fetchGameMeta(
  source: GameSource,
  id: number,
): Promise<GameMeta | null> {
  const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001';
  try {
    const res = await fetch(
      `${backendUrl}/api/openings/games/${id}/meta?source=${source}`,
      { next: { revalidate: 3600 } },
    );
    if (!res.ok) return null;
    return (await res.json()) as GameMeta;
  } catch {
    return null;
  }
}
