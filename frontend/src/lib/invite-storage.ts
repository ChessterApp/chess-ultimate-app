/**
 * Client-side storage key for the invite JWT.
 *
 * The sign-up page stashes the invite JWT here before handing off to Clerk, so
 * the `no_link` polling component can replay it to `/api/chess-empire/link/claim`
 * if Clerk drops `unsafeMetadata` during an OAuth (Google/Apple) redirect. The
 * JWT's own `exp` is the safety bound — a stale value simply claims as expired
 * and is cleared. Not `server-only`: imported by client components.
 */
export const CE_INVITE_JWT_STORAGE_KEY = 'ce_invite_jwt';
