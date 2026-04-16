'use client';

import { useState, useEffect, createContext, useContext } from 'react';
import { useAuth } from '@clerk/nextjs';
import { LOCAL_FIRST_SUBSCRIPTION } from '@/lib/feature-flags';
import { useQuery } from '@powersync/react';

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
 * Reads subscription status from local SQLite via @powersync/react useQuery.
 */
function useSubscriptionPowerSync(userId: string | undefined): SubscriptionState {
  const { data, isLoading } = useQuery(
    'SELECT * FROM subscriptions WHERE clerk_user_id = ?',
    [userId ?? ''],
  );

  if (!userId) {
    return { loading: false, active: false, plan: null, status: null, trialEnd: null };
  }

  if (isLoading) {
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
  const { isSignedIn, userId } = useAuth();
  if (LOCAL_FIRST_SUBSCRIPTION) {
    return useSubscriptionPowerSync(userId ?? undefined);
  }
  return useSubscriptionLegacy(isSignedIn);
}
