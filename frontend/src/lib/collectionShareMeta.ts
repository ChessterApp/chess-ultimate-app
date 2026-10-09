/**
 * collectionShareMeta — server-side helpers for the `/g/c/<token>` short-link
 * OG cards (a shared My Games *collection*).
 *
 * Mirrors `gameShareMeta` but for a whole collection: the PUBLIC
 * `/api/games/collection/shared/<token>/meta` endpoint returns only the owner
 * display name and game count — never any game data. Builders are split from
 * the network fetch so they can be unit-tested without a running backend.
 */

export interface CollectionMeta {
  owner_name?: string | null;
  game_count?: number | null;
}

/**
 * Public base URL of the Flask backend, used for ABSOLUTE asset URLs that
 * external crawlers fetch directly (e.g. OG images). Must be the publicly
 * reachable host so WhatsApp/Telegram can load the thumbnail — never localhost.
 */
function publicBackendUrl(): string {
  return process.env.NEXT_PUBLIC_BACKEND_URL || 'https://api.chesster.io';
}

/** Absolute URL of a shared collection's board-position OG thumbnail (PNG). */
export function sharedCollectionThumbnailUrl(token: string): string {
  return `${publicBackendUrl()}/api/games/collection/shared/${encodeURIComponent(token)}/thumbnail.png`;
}

/**
 * Fetch public metadata for a shared collection by its share token. Hits the
 * PUBLIC `/api/games/collection/shared/<token>/meta` endpoint — owner name and
 * game count only. Never throws — returns null on any network/HTTP error
 * (unknown or revoked token → 404 → null) so `generateMetadata` can fall back
 * cleanly.
 */
export async function fetchSharedCollectionMeta(
  token: string,
): Promise<CollectionMeta | null> {
  const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001';
  try {
    const res = await fetch(
      `${backendUrl}/api/games/collection/shared/${encodeURIComponent(token)}/meta`,
      { next: { revalidate: 300 } },
    );
    if (!res.ok) return null;
    return (await res.json()) as CollectionMeta;
  } catch {
    return null;
  }
}
