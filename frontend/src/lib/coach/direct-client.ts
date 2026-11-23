/**
 * The page's side of the voice pipeline's direct path (23.11; the pass: src/lib/coach/direct-pass.ts, Hermes'
 * check: hermes/src/direct_access.py). The two hot requests of a spoken turn — the phrase's hearing and the question —
 * go straight to Hermes with the pass; anything else, and any failure before the answer starts, goes through the site
 * as before. A path that failed is left alone for a while, so a broken one does not cost every turn a try.
 */

export type DirectPass = { url: string; token: string; expiresAt: number };

/** A pass is renewed this long before it runs out (a turn in flight never carries a stale one). */
const RENEW_BEFORE_MS = 60_000;
/** After a failure the direct path rests this long. */
const REST_AFTER_FAILURE_MS = 120_000;
/** A pass that would not come is asked again only after this. */
const REST_AFTER_NO_PASS_MS = 60_000;
/** A direct request that has not started answering by then goes through the site instead. */
const CONNECT_TIMEOUT_MS = 8_000;

let pass: DirectPass | null = null;
let pending: Promise<DirectPass | null> | null = null;
let restUntil = 0;
let off = false; // the deployment has no direct path: { direct: null }

function now(): number {
  return Date.now();
}

/** The pass for the direct path, asked of the site when the one in hand runs out; null when the path is off. */
export async function directPass(): Promise<DirectPass | null> {
  if (off || now() < restUntil) return null;
  if (pass && pass.expiresAt - RENEW_BEFORE_MS > now()) return pass;
  if (!pending) {
    pending = (async () => {
      try {
        const res = await fetch('/api/coach/direct-pass', { credentials: 'include', cache: 'no-store' });
        if (!res.ok) throw new Error(`pass ${res.status}`);
        const data = (await res.json()) as { direct?: DirectPass | null };
        const got = data?.direct;
        if (!got || typeof got.url !== 'string' || typeof got.token !== 'string' || typeof got.expiresAt !== 'number') {
          off = data?.direct === null;
          pass = null;
          return null;
        }
        pass = got;
        return got;
      } catch {
        restUntil = now() + REST_AFTER_NO_PASS_MS;
        pass = null;
        return null;
      } finally {
        pending = null;
      }
    })();
  }
  return pending;
}

/** Asks for the pass ahead (the voice starts): the first spoken turn does not wait for it. */
export function warmDirect(): void {
  void directPass();
}

/**
 * POST *path* (`voice/stt` or `chat`) straight to Hermes. Null — go through the site — when the path is off or
 * resting, the network failed, or Hermes refused before answering (a refusal through the site then reads as usual).
 */
export async function directPost(path: 'voice/stt' | 'chat', init: RequestInit): Promise<Response | null> {
  const p = await directPass();
  if (!p) return null;
  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), CONNECT_TIMEOUT_MS);
  // The caller's stop reaches the request — and its streamed answer — through this one signal.
  const outer = init.signal;
  const onAbort = () => timeout.abort();
  if (outer?.aborted) timeout.abort();
  else outer?.addEventListener('abort', onAbort, { once: true });
  try {
    const headers = new Headers(init.headers);
    headers.set('Authorization', `Bearer ${p.token}`);
    const res = await fetch(`${p.url}/direct/${path}`, { ...init, headers, credentials: 'omit', signal: timeout.signal });
    clearTimeout(timer);
    if (res.ok) {
      // The answer may stream past the connect timeout: from here on only the caller stops it.
      return res;
    }
    outer?.removeEventListener('abort', onAbort);
    if (res.status === 401) pass = null; // a pass the server did not take: a new one next time
    // A limit, no credit or too long an utterance is the student's, not the path's: the site tells it as usual.
    else if (![402, 413, 429].includes(res.status)) restUntil = now() + REST_AFTER_FAILURE_MS;
    return null;
  } catch (err) {
    clearTimeout(timer);
    outer?.removeEventListener('abort', onAbort);
    if (outer?.aborted) throw err;
    restUntil = now() + REST_AFTER_FAILURE_MS;
    return null;
  }
}

/** Counts a message the direct path sent, as the site's chat proxy counts its own (off the turn's path). */
export function countDirectMessage(): void {
  try {
    if (typeof navigator !== 'undefined' && navigator.sendBeacon && navigator.sendBeacon('/api/coach/direct-pass')) return;
  } catch {
    // fall through
  }
  void fetch('/api/coach/direct-pass', { method: 'POST', credentials: 'include', keepalive: true }).catch(() => undefined);
}

/** Tests only. */
export function resetDirectForTests(): void {
  pass = null;
  pending = null;
  restUntil = 0;
  off = false;
}
