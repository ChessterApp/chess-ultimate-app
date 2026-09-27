'use client';

/**
 * Client-side fallback for the Phase 3 API guard (`requireApiAccess`).
 *
 * The primary defense is the Phase 1 route guard — a restricted (frozen/expired)
 * member never reaches a gated page. This handles the edge cases the route guard
 * can't: a direct API call, a stale tab, or an in-flight request when a link is
 * frozen mid-session. When a gated API answers `403 MEMBERSHIP_RESTRICTED`, we
 * send the user to the upgrade path from the response so the client neither
 * crashes nor spins.
 */

export interface RestrictedInfo {
  reason: string | null;
  upgradePath: string;
}

/**
 * Inspect a response for a `MEMBERSHIP_RESTRICTED` 403 body. Returns the
 * restriction info (with a `/dashboard` fallback upgrade path) or null. Reads a
 * clone so the caller can still consume the original body.
 */
export async function readRestricted(
  res: Response,
): Promise<RestrictedInfo | null> {
  if (res.status !== 403) return null;
  try {
    const data = await res.clone().json();
    if (data && data.error === 'MEMBERSHIP_RESTRICTED') {
      const upgradePath =
        typeof data.upgradePath === 'string' && data.upgradePath
          ? data.upgradePath
          : '/dashboard';
      return { reason: data.reason ?? null, upgradePath };
    }
  } catch {
    // Not a JSON body — not our restriction envelope.
  }
  return null;
}

/**
 * If `res` is a membership-restricted 403, redirect the browser to the upgrade
 * path and return true (the caller should stop processing). Otherwise false.
 */
export async function handleRestrictedResponse(res: Response): Promise<boolean> {
  const info = await readRestricted(res);
  if (!info) return false;
  if (typeof window !== 'undefined') {
    window.location.href = info.upgradePath;
  }
  return true;
}
