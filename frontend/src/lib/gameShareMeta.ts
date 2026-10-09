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
 * Public base URL of the Flask backend, used for ABSOLUTE asset URLs that
 * external crawlers fetch directly (e.g. OG images). Unlike the server-side
 * `BACKEND_URL` (which may be localhost), this must be the publicly reachable
 * host so WhatsApp/Telegram can load the thumbnail.
 */
function publicBackendUrl(): string {
  return process.env.NEXT_PUBLIC_BACKEND_URL || 'https://api.chesster.io';
}

/** Absolute URL of a master game's board-position OG thumbnail (PNG). */
export function masterThumbnailUrl(source: GameSource, id: number): string {
  return `${publicBackendUrl()}/api/openings/games/${id}/thumbnail.png?source=${source}`;
}

/** Absolute URL of a shared user game's board-position OG thumbnail (PNG). */
export function sharedThumbnailUrl(token: string): string {
  return `${publicBackendUrl()}/api/games/shared/${encodeURIComponent(token)}/thumbnail.png`;
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

/**
 * Fetch public metadata for a shared *user* game by its share token. Hits the
 * PUBLIC `/api/games/shared/<token>/meta` endpoint — header fields only, never
 * the PGN. Never throws — returns null on any network/HTTP error (unknown or
 * revoked token → 404 → null) so `generateMetadata` can fall back cleanly.
 */
export async function fetchSharedGameMeta(
  token: string,
): Promise<GameMeta | null> {
  const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001';
  try {
    const res = await fetch(
      `${backendUrl}/api/games/shared/${encodeURIComponent(token)}/meta`,
      { next: { revalidate: 300 } },
    );
    if (!res.ok) return null;
    return (await res.json()) as GameMeta;
  } catch {
    return null;
  }
}
