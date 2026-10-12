/**
 * Finished-run outbox: a signed-in run is queued before `POST /runs/finish`
 * and dequeued once the server has it, so a failed send (or a closed tab) is
 * retried on the next page load. `/runs/finish` is idempotent on run_id, so a
 * resend after a lost response is harmless.
 *
 * Framework-free (shared with the mobile app): pass any sync key-value store
 * (localStorage on web).
 */

import type { FinishRequest, FinishResponse } from './types';

export interface KeyValueStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export const OUTBOX_KEY = 'puzzleRush.finishOutbox';
/** Oldest entries are dropped beyond this. */
export const OUTBOX_MAX = 20;

interface OutboxEntry {
  userId: string;
  body: FinishRequest;
}

function load(store: KeyValueStore): OutboxEntry[] {
  try {
    const v = JSON.parse(store.getItem(OUTBOX_KEY) || '[]');
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

function save(store: KeyValueStore, entries: OutboxEntry[]) {
  try {
    if (entries.length) store.setItem(OUTBOX_KEY, JSON.stringify(entries.slice(-OUTBOX_MAX)));
    else store.removeItem(OUTBOX_KEY);
  } catch {
    // Quota / private mode: the outbox is best-effort.
  }
}

export function enqueueFinish(store: KeyValueStore, userId: string, body: FinishRequest) {
  save(store, [...load(store).filter((e) => e.body.run_id !== body.run_id), { userId, body }]);
}

export function dequeueFinish(store: KeyValueStore, runId: string) {
  save(store, load(store).filter((e) => e.body.run_id !== runId));
}

/** Queued runs belonging to `userId` (never resent under another account). */
export function pendingFinishes(store: KeyValueStore, userId: string): FinishRequest[] {
  return load(store).filter((e) => e.userId === userId).map((e) => e.body);
}

/** A 4xx the server will never accept (bad body, someone else's run id). */
function isPermanent(e: unknown): boolean {
  const status = (e as { status?: unknown })?.status;
  return typeof status === 'number' && status >= 400 && status < 500 && ![401, 408, 429].includes(status);
}

/**
 * Resend every queued run of `userId`, one at a time. Sent (and permanently
 * rejected) runs leave the outbox; transient failures stay for next time.
 */
export async function flushOutbox(
  store: KeyValueStore,
  userId: string,
  send: (body: FinishRequest) => Promise<FinishResponse>,
): Promise<FinishResponse[]> {
  const sent: FinishResponse[] = [];
  for (const body of pendingFinishes(store, userId)) {
    try {
      sent.push(await send(body));
      dequeueFinish(store, body.run_id);
    } catch (e) {
      if (isPermanent(e)) dequeueFinish(store, body.run_id);
    }
  }
  return sent;
}
