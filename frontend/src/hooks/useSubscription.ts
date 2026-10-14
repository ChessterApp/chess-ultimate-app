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
function useSubscriptionPowerSync(isLoaded: boolean | undefined, userId: string | undefined): SubscriptionState {
  const { data, isLoading } = useQuery(
    'SELECT * FROM subscriptions WHERE clerk_user_id = ?',
    [userId ?? ''],
  );

  if (!isLoaded) {
    return { loading: true, active: false, plan: null, status: null, trialEnd: null };
  }

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

const LOADING: SubscriptionState = { loading: true, active: false, plan: null, status: null, trialEnd: null };
const INACTIVE: SubscriptionState = { loading: false, active: false, plan: null, status: null, trialEnd: null };

/**
 * Legacy fetch-based subscription fetch.
 *
 * The state is derived per render: until Clerk has loaded, and until
 * /api/subscription/status has answered for the current user, it is
 * `loading`. Before, the effect stored "not loading, inactive" while Clerk was
 * still loading, so the first signed-in render showed the paywall to premium
 * users until the status call returned (2026-10-14).
 */
function useSubscriptionLegacy(
  isLoaded: boolean | undefined,
  isSignedIn: boolean | undefined,
  userId: string | null | undefined,
): SubscriptionState {
  const [result, setResult] = useState<{ userId: string; state: SubscriptionState } | null>(null);

  useEffect(() => {
    if (!isLoaded || !isSignedIn || !userId) return;
    let cancelled = false;
    fetch('/api/subscription/status')
      .then(res => res.json())
      .then(data => {
        if (cancelled) return;
        setResult({
          userId,
          state: {
            loading: false,
            active: data.active || false,
            plan: data.plan || null,
            status: data.status || null,
            trialEnd: data.trialEnd || null,
          },
        });
      })
      .catch(() => {
        if (!cancelled) setResult({ userId, state: INACTIVE });
      });
    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, userId]);

  if (!isLoaded) return LOADING;
  if (!isSignedIn || !userId) return INACTIVE;
  if (!result || result.userId !== userId) return LOADING;
  return result.state;
}

export function useSubscriptionFetch(): SubscriptionState {
  const { isLoaded, isSignedIn, userId } = useAuth();
  // Feature flag is a module-level constant, so hook order is stable across renders.
  if (LOCAL_FIRST_SUBSCRIPTION) {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    return useSubscriptionPowerSync(isLoaded, userId ?? undefined);
  }
  // eslint-disable-next-line react-hooks/rules-of-hooks
  return useSubscriptionLegacy(isLoaded, isSignedIn, userId);
}
