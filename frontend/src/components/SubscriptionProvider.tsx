'use client';

import { ReactNode } from 'react';
import { SubscriptionContext, useSubscriptionFetch } from '@/hooks/useSubscription';

export default function SubscriptionProvider({ children }: { children: ReactNode }) {
  const subscription = useSubscriptionFetch();
  return (
    <SubscriptionContext.Provider value={subscription}>
      {children}
    </SubscriptionContext.Provider>
  );
}
