'use client';

import { useState, useEffect, createContext, useContext } from 'react';
import { useAuth } from '@clerk/nextjs';

interface SubscriptionState {
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

export function useSubscriptionFetch(): SubscriptionState {
  const { isSignedIn } = useAuth();
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
