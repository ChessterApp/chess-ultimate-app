import { useCallback, useEffect, useRef, useState } from 'react';

export const POLL_INTERVAL_MS = 2000;
export const POLL_TIMEOUT_MS = 60000;

export type SubscriptionStatus = { active: boolean; plan?: string | null };
export type PollResult = { status: 'active'; plan: string | null } | { status: 'timeout' };

export interface PollOptions {
  fetchStatus: () => Promise<SubscriptionStatus>;
  intervalMs?: number;
  timeoutMs?: number;
  /** Injected for tests; defaults to setTimeout / Date.now. */
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
  signal?: AbortSignal;
}

const defaultSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * Poll the subscription status until it reports active or the timeout
 * elapses. Fetch errors are treated as "not yet" — the Whop webhook may lag
 * the redirect, so only the deadline ends the loop. Resolves `timeout` early
 * if `signal` aborts.
 */
export async function pollSubscription({
  fetchStatus,
  intervalMs = POLL_INTERVAL_MS,
  timeoutMs = POLL_TIMEOUT_MS,
  sleep = defaultSleep,
  now = Date.now,
  signal,
}: PollOptions): Promise<PollResult> {
  const deadline = now() + timeoutMs;
  while (!signal?.aborted) {
    try {
      const res = await fetchStatus();
      if (res.active) return { status: 'active', plan: res.plan ?? null };
    } catch {
      // keep polling until the deadline
    }
    if (now() + intervalMs > deadline) break;
    await sleep(intervalMs);
  }
  return { status: 'timeout' };
}

async function fetchSubscriptionStatus(): Promise<SubscriptionStatus> {
  const res = await fetch('/api/subscription/status', { cache: 'no-store' });
  if (!res.ok) throw new Error(`status ${res.status}`);
  return res.json();
}

export type ActivationState =
  | { phase: 'loading' }
  | { phase: 'success'; plan: string | null }
  | { phase: 'timeout' };

/** Runs `pollSubscription` against the status API; `retry` restarts it. */
export function useSubscriptionActivation(): { state: ActivationState; retry: () => void } {
  const [state, setState] = useState<ActivationState>({ phase: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    pollSubscription({ fetchStatus: fetchSubscriptionStatus, signal: controller.signal }).then(
      (result) => {
        if (controller.signal.aborted) return;
        setState(result.status === 'active' ? { phase: 'success', plan: result.plan } : { phase: 'timeout' });
      },
    );
    return () => controller.abort();
  }, [attempt]);

  const retry = useCallback(() => {
    controllerRef.current?.abort();
    setState({ phase: 'loading' });
    setAttempt((n) => n + 1);
  }, []);

  return { state, retry };
}
