import type { Locale } from '@/i18n/config';

type ClerkUserLike = {
  unsafeMetadata?: Record<string, unknown>;
  update: (params: { unsafeMetadata: Record<string, unknown> }) => Promise<unknown>;
};

/** Cap on how long a locale switch waits for the Clerk write before reloading. */
export const PERSIST_WAIT_MS = 1000;

/**
 * Save the picked locale as `preferred_locale` in the signed-in user's Clerk
 * `unsafeMetadata` (so emails can use it later). Reads the user from the
 * global `window.Clerk` instead of `useUser()` so the switcher keeps working
 * outside a ClerkProvider. Never rejects and resolves within PERSIST_WAIT_MS,
 * so the caller can await it before reloading without blocking the switch —
 * a reload would otherwise abort the in-flight request.
 */
export function persistPreferredLocale(locale: Locale): Promise<void> {
  if (typeof window === 'undefined') return Promise.resolve();
  const user = (window as unknown as { Clerk?: { user?: ClerkUserLike | null } }).Clerk?.user;
  if (!user) return Promise.resolve();

  let write: Promise<unknown>;
  try {
    write = user.update({ unsafeMetadata: { ...user.unsafeMetadata, preferred_locale: locale } });
  } catch {
    return Promise.resolve();
  }
  return Promise.race([
    write.then(() => undefined, () => undefined),
    new Promise<void>((resolve) => setTimeout(resolve, PERSIST_WAIT_MS)),
  ]);
}
