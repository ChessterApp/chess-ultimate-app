/**
 * Once-per-course guard for the level-complete conversion screen. Returns true
 * the FIRST time a given course completion is seen (and records it), false on
 * every later call — so revisiting a completed lesson never re-fires the overlay.
 *
 * Pure aside from the injected storage, so it's unit-testable without a DOM.
 * Defaults to `window.localStorage`; returns false when no storage is available
 * (e.g. SSR) rather than throwing.
 */
export function shouldShowLevelComplete(
  courseId: string,
  storage?: Pick<Storage, 'getItem' | 'setItem'>,
): boolean {
  const store =
    storage ?? (typeof window !== 'undefined' ? window.localStorage : null);
  if (!store) return false;

  const key = `level-complete-shown-${courseId}`;
  if (store.getItem(key)) return false;
  store.setItem(key, '1');
  return true;
}
