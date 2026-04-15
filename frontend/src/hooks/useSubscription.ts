'use client';

import { useState, useEffect, createContext, useContext } from 'react';
import { useAuth } from '@clerk/nextjs';
import { LOCAL_FIRST_SUBSCRIPTION } from '@/lib/feature-flags';
import { usePowerSyncContext } from '@/lib/powersync/PowerSyncProvider';
import { useLiveQuery } from '@tanstack/react-db';
import { eq } from '@tanstack/db';

export interface SubscriptionState {
  loading: boolean;
  active: boolean;
  plan: string | null;
  status: string | null;
  trialEnd: string | null;
}

const SubscriptionContext = createContext<SubscriptionState>({
  loading: true,
  active: false,
  plan: null,
  status: null,
  trialEnd: null,
});

export function useSubscription() {
  return useContext(SubscriptionContext);
}

export { SubscriptionContext };

/**
 * PowerSync-backed subscription fetch.
 * Reads subscription status from local SQLite via TanStack DB live query.
 */
function useSubscriptionPowerSync(userId: string | undefined): SubscriptionState {
  const { collections, isReady } = usePowerSyncContext();

  const { data, isLoading } = useLiveQuery(
    (q) => {
      if (!collections || !isReady || !userId) return null;
      return q
        .from({ s: collections.subscriptions })
        .where(({ s }) => eq(s.user_id, userId))
        .select(({ s }) => ({
          id: s.id,
          active: s.active,
          plan: s.plan,
          status: s.status,
          trial_end: s.trial_end,
        }));
    },
    [collections, isReady, userId],
  );

  if (!userId) {
    return { loading: false, active: false, plan: null, status: null, trialEnd: null };
  }

  if (isLoading || !isReady) {
    return { loading: true, active: false, plan: null, status: null, trialEnd: null };
  }

  const row = data?.[0] as { id: string; active: number | null; plan: string | null; status: string | null; trial_end: string | null } | undefined;
  if (!row) {
    return { loading: false, active: false, plan: null, status: null, trialEnd: null };
  }

  return {
    loading: false,
    active: row.active === 1,
    plan: row.plan ?? null,
    status: row.status ?? null,
    trialEnd: row.trial_end ?? null,
  };
}

/**
 * Legacy fetch-based subscription fetch.
 */
function useSubscriptionLegacy(isSignedIn: boolean | undefined): SubscriptionState {
  const [state, setState] = useState<SubscriptionState>({
    loading: true,
    active: false,
    plan: null,
    status: null,
    trialEnd: null,
  });

  useEffect(() => {
    if (!isSignedIn) {
      setState({ loading: false, active: false, plan: null, status: null, trialEnd: null });
      return;
    }

    fetch('/api/subscription/status')
      .then(res => res.json())
      .then(data => {
        setState({
          loading: false,
          active: data.active || false,
          plan: data.plan || null,
          status: data.status || null,
          trialEnd: data.trialEnd || null,
        });
      })
      .catch(() => {
        setState({ loading: false, active: false, plan: null, status: null, trialEnd: null });
      });
  }, [isSignedIn]);

  return state;
}

export function useSubscriptionFetch(): SubscriptionState {
  const { isSignedIn } = useAuth();
  // PowerSync path disabled: @tanstack/react-db useLiveQuery lacks
  // getServerSnapshot for SSR, causing HTTP 500. Re-enable when fixed.
  return useSubscriptionLegacy(isSignedIn);
}
