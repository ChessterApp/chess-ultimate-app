/**
 * The coach page's "current session" id, kept in localStorage per Clerk user.
 *
 * It used to live under one shared key, so after an account switch in the same
 * browser the next user restored the previous user's session id — and Hermes,
 * which checks ownership, answered 404 on every /boards and /messages call
 * (2026-10-14). The key now carries the user id. The legacy key is moved over
 * once; if it belonged to someone else, the restore's "Session not found"
 * drops it.
 */

export const LEGACY_SESSION_KEY = 'coach-session-id';

export function sessionKey(userId: string): string {
  return `${LEGACY_SESSION_KEY}:${userId}`;
}

export function loadSessionId(userId: string): string | null {
  const key = sessionKey(userId);
  const saved = localStorage.getItem(key);
  if (saved) return saved;
  const legacy = localStorage.getItem(LEGACY_SESSION_KEY);
  if (!legacy) return null;
  localStorage.removeItem(LEGACY_SESSION_KEY);
  localStorage.setItem(key, legacy);
  return legacy;
}

export function saveSessionId(userId: string, sessionId: string): void {
  localStorage.setItem(sessionKey(userId), sessionId);
}

export function clearSessionId(userId: string): void {
  localStorage.removeItem(sessionKey(userId));
}
