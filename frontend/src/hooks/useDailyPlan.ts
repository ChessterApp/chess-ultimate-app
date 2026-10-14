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

/** Today's plan for the coach's home, fetched once while `enabled`. */
export function useDailyPlan(enabled: boolean): DailyPlanState {
  const [state, setState] = useState<DailyPlanState>(enabled ? { status: 'loading' } : OFF);

  useEffect(() => {
    if (!enabled) return;
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
    };
  }, [enabled]);

  return enabled ? state : OFF;
}
