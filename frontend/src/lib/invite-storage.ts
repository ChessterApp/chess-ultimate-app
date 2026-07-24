/**
 * Client-side storage keys + helpers for the Chess Empire onboarding handoff.
 *
 * The sign-up page stashes the invite JWT here before handing off to Clerk, so
 * the `no_link` polling component can replay it to `/api/chess-empire/link/claim`
 * if Clerk drops `unsafeMetadata` during an OAuth (Google/Apple) redirect. The
 * JWT's own `exp` is the safety bound — a stale value simply claims as expired
 * and is cleared.
 *
 * The welcome-URL key records where the find-yourself → confirm flow started so
 * that, on a white-label domain, a bare sign-up (no valid invite JWT) can be
 * bounced back to re-do onboarding instead of registering unlinked.
 *
 * Not `server-only`: imported by client components.
 */
export const CE_INVITE_JWT_STORAGE_KEY = 'ce_invite_jwt';
export const CE_WELCOME_URL_STORAGE_KEY = 'ce_welcome_url';
/**
 * Durable (localStorage) copy of the branch welcome URL, stashed at the confirm
 * step so the dashboard's no-link screen can offer a "start over" link even
 * after an OAuth round-trip cleared sessionStorage.
 */
export const CE_BRANCH_WELCOME_URL_STORAGE_KEY = 'ce_branch_welcome_url';

/**
 * Persist the current welcome-flow URL/path so the sign-up guard can send an
 * abandoned onboarding back to where it started. Best-effort — storage may be
 * disabled (private mode / blocked).
 */
export function persistWelcomeOnboardingUrl(url: string): void {
  try {
    sessionStorage.setItem(CE_WELCOME_URL_STORAGE_KEY, url);
  } catch {
    // Storage disabled — the guard falls back to the org welcome landing.
  }
}

/** Read the stored welcome-flow URL, or null if none / storage unavailable. */
export function readWelcomeOnboardingUrl(): string | null {
  try {
    return sessionStorage.getItem(CE_WELCOME_URL_STORAGE_KEY);
  } catch {
    return null;
  }
}

/**
 * Persist the branch welcome URL durably (localStorage) so the no-link "start
 * over" link survives an OAuth round-trip. Best-effort.
 */
export function persistBranchWelcomeUrl(url: string): void {
  try {
    localStorage.setItem(CE_BRANCH_WELCOME_URL_STORAGE_KEY, url);
  } catch {
    // Storage disabled — the "start over" link simply won't render.
  }
}

/** Read the durable branch welcome URL, or null if none / storage unavailable. */
export function readBranchWelcomeUrl(): string | null {
  try {
    return localStorage.getItem(CE_BRANCH_WELCOME_URL_STORAGE_KEY);
  } catch {
    return null;
  }
}

/**
 * Clear every trace of an in-flight invite/onboarding so a blocked bare sign-up
 * can't later replay stale state. Wipes the invite JWT from both storages and
 * the stored welcome URLs.
 */
export function clearInviteOnboardingState(): void {
  try {
    sessionStorage.removeItem(CE_INVITE_JWT_STORAGE_KEY);
    localStorage.removeItem(CE_INVITE_JWT_STORAGE_KEY);
    sessionStorage.removeItem(CE_WELCOME_URL_STORAGE_KEY);
    localStorage.removeItem(CE_BRANCH_WELCOME_URL_STORAGE_KEY);
  } catch {
    // Storage disabled — nothing to clear.
  }
}
