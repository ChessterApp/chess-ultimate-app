'use client';

/**
 * Client context carrying the current user's membership state and its derived
 * access policy. The state is resolved server-side in the root layout
 * (`resolveMembershipState`) and passed in, so this provider does no fetching.
 *
 * `useMembership()` defaults to full access, so any component rendered outside
 * the provider (or for an unauthenticated / non-member user) behaves normally.
 */
import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { getAccessPolicy, type AccessPolicy } from '@/lib/access-policy';
import type { MembershipState } from '@/lib/chess-empire-member';

interface MembershipContextValue {
  state: MembershipState | null;
  policy: AccessPolicy;
}

const MembershipContext = createContext<MembershipContextValue>({
  state: null,
  policy: getAccessPolicy(null),
});

export function useMembership(): MembershipContextValue {
  return useContext(MembershipContext);
}

export function MembershipProvider({
  state,
  personalSubActive = false,
  children,
}: {
  state: MembershipState | null;
  /** Personal-subscription override — lifts a frozen/expired restriction. */
  personalSubActive?: boolean;
  children: ReactNode;
}) {
  const value = useMemo<MembershipContextValue>(
    () => ({ state, policy: getAccessPolicy(state, personalSubActive) }),
    [state, personalSubActive],
  );
  return (
    <MembershipContext.Provider value={value}>
      {children}
    </MembershipContext.Provider>
  );
}
