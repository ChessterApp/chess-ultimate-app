import { useEffect, useState } from 'react';
import { parseDailyPlan, type DailyPlan } from '@/lib/coach/tool-summary';

export type DailyPlanState =
  | { status: 'off' }
  | { status: 'loading' }
  | { status: 'ready'; plan: DailyPlan }
  /** No plan (the request failed, or nothing this client can show): the starter prompts stand in. */
  | { status: 'error' };

const OFF: DailyPlanState = { status: 'off' };
const TIMEOUT_MS = 6000;

/**
 * Today's plan for the coach's home, fetched while `enabled` each time the home is `shown` (an empty session): the
 * plan is of now — «Разбор последней партии» names the latest game — so a new session after a game asks again, with
 * the skeleton meanwhile: a card of the earlier plan cannot be tapped. `session` — the session the home belongs to.
 */
export function useDailyPlan(enabled: boolean, shown = true, session: string | null = null): DailyPlanState {
  const [state, setState] = useState<DailyPlanState>(enabled ? { status: 'loading' } : OFF);

  useEffect(() => {
    if (!enabled || !shown) return;
    let cancelled = false;
    const signal = typeof AbortSignal.timeout === 'function' ? AbortSignal.timeout(TIMEOUT_MS) : undefined;
    fetch('/api/coach/daily-plan', { signal })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: unknown) => {
        if (cancelled) return;
        const plan = parseDailyPlan(data);
        setState(plan ? { status: 'ready', plan } : { status: 'error' });
      })
      .catch(() => {
        if (!cancelled) setState({ status: 'error' });
      });
    return () => {
      cancelled = true;
      // The home is hidden (the first message of the session): the plan read for it is spent — the next home
      // starts from the skeleton, not from this one for a frame.
      setState({ status: 'loading' });
    };
    // `session`: another session whose thread is empty too (a game played without remarks, then «Новая сессия»)
    // is another home.
  }, [enabled, shown, session]);

  return enabled ? state : OFF;
}
