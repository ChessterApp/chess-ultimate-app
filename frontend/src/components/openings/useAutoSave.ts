/**
 * useAutoSave — debounced, serialized auto-save for an editable document.
 *
 * The caller describes the unsaved state as `entry` ({ key, value }, or null when
 * there is nothing to save) inside a `scope` (e.g. the open tab). Every new key
 * restarts the debounce; saves run one at a time, so an edit made while a save is
 * in flight is saved afterwards instead of racing it. Changing scope flushes the
 * previous scope's pending edit immediately, as do flush(), page hide and unmount.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

export interface AutoSaveEntry<T> {
  key: string;
  value: T;
}

interface QueuedEntry<T> extends AutoSaveEntry<T> {
  scope: string | null;
}

export interface UseAutoSaveOptions<T> {
  scope: string | null;
  entry: AutoSaveEntry<T> | null;
  save: (value: T) => Promise<boolean>;
  /** Called after a save whose content still matches the current entry. */
  onClean?: (value: T) => void;
  delayMs?: number;
  /** beforeunload prompt text (most browsers show their own wording). */
  leaveWarning?: string;
}

const SAVED_FADE_MS = 3000;

export function useAutoSave<T>({ scope, entry, save, onClean, delayMs = 1500, leaveWarning = '' }: UseAutoSaveOptions<T>) {
  const [status, setStatus] = useState<SaveStatus>('idle');

  const saveRef = useRef(save);
  const onCleanRef = useRef(onClean);
  const leaveWarningRef = useRef(leaveWarning);
  useEffect(() => {
    saveRef.current = save;
    onCleanRef.current = onClean;
    leaveWarningRef.current = leaveWarning;
  });

  const latestRef = useRef<QueuedEntry<T> | null>(null);
  const pendingRef = useRef<QueuedEntry<T> | null>(null);
  const failedRef = useRef<QueuedEntry<T> | null>(null);
  const chainRef = useRef<Promise<void>>(Promise.resolve());
  const activeRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fadeRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
  };

  const enqueue = useCallback((queued: QueuedEntry<T>) => {
    activeRef.current++;
    if (fadeRef.current) clearTimeout(fadeRef.current);
    setStatus('saving');
    chainRef.current = chainRef.current.then(async () => {
      let ok = false;
      try {
        ok = await saveRef.current(queued.value);
      } catch {
        ok = false;
      }
      activeRef.current--;
      if (ok) {
        if (failedRef.current?.scope === queued.scope) failedRef.current = null;
        const latest = latestRef.current;
        if (latest && latest.scope === queued.scope && latest.key === queued.key) {
          onCleanRef.current?.(queued.value);
        }
      } else if (pendingRef.current?.scope !== queued.scope) {
        // Keep it for Retry unless a newer edit of the same document is waiting.
        failedRef.current = queued;
      }
      if (activeRef.current > 0) return;
      setStatus(ok ? 'saved' : 'error');
      if (ok) fadeRef.current = setTimeout(() => setStatus(s => (s === 'saved' ? 'idle' : s)), SAVED_FADE_MS);
    });
  }, []);

  /** Saves anything pending (or a failed save) now; resolves true when all saves succeeded. */
  const flush = useCallback((): Promise<boolean> => {
    clearTimer();
    const failed = failedRef.current;
    const pending = pendingRef.current;
    failedRef.current = null;
    pendingRef.current = null;
    if (failed && failed.scope !== pending?.scope) enqueue(failed);
    if (pending) enqueue(pending);
    return chainRef.current.then(() => failedRef.current === null);
  }, [enqueue]);

  /** Forgets pending and failed saves, e.g. when the document was deleted. */
  const discard = useCallback(() => {
    clearTimer();
    pendingRef.current = null;
    failedRef.current = null;
    setStatus('idle');
  }, []);

  const hasUnsaved = useCallback(
    () => pendingRef.current !== null || failedRef.current !== null || activeRef.current > 0,
    [],
  );

  const scopeRef = useRef(scope);
  const keyRef = useRef<string | null>(null);
  const entryKey = entry?.key ?? null;
  useEffect(() => {
    const scopeChanged = scopeRef.current !== scope;
    const keyChanged = keyRef.current !== entryKey;
    scopeRef.current = scope;
    keyRef.current = entryKey;
    latestRef.current = entry ? { ...entry, scope } : null;
    if (!scopeChanged && !keyChanged) return;
    // Save the previous document before tracking the new one.
    if (scopeChanged && pendingRef.current) flush();

    if (!entry) {
      // Same document became clean / unsavable: nothing left to save.
      if (pendingRef.current?.scope === scope) {
        pendingRef.current = null;
        clearTimer();
      }
      return;
    }
    pendingRef.current = { ...entry, scope };
    clearTimer();
    timerRef.current = setTimeout(() => { flush(); }, delayMs);
    // entry is read through its key; scope/key changes are what matter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, entryKey, flush, delayMs]);

  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') flush();
    };
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!hasUnsaved()) return;
      flush();
      e.preventDefault();
      e.returnValue = leaveWarningRef.current;
    };
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('beforeunload', onBeforeUnload);
      if (fadeRef.current) clearTimeout(fadeRef.current);
      flush();
    };
  }, [flush, hasUnsaved]);

  return { status, flush, discard, hasUnsaved };
}
