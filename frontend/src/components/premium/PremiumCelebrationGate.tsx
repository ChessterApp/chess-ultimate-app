'use client';

import { useEffect, useState } from 'react';
import { useUser } from '@clerk/nextjs';
import PremiumCelebration from './PremiumCelebration';

/**
 * Gate that shows the one-time premium welcome ceremony exactly once.
 *
 * On sign-in it fetches the caller's subscription status and the "seen" flag in
 * parallel. The ceremony renders only when the personal subscription is active
 * AND the flag is still false — so it fires for comp rows and real Whop
 * purchases alike, with no hardcoded users. Dismissing POSTs the flag so it
 * never shows again.
 *
 * Fail-safe by design: any fetch error (or either response not being OK)
 * renders nothing and never blocks the app. Nothing renders until both
 * responses have arrived, so there is no flash.
 */

interface SubscriptionStatus {
  active?: boolean;
  plan?: string | null;
  currentPeriodEnd?: string | null;
}

/** Human label for the receipt's Plan row from the raw subscription plan. */
export function planLabel(plan: string | null | undefined): string {
  if (!plan) return 'Premium · all features';
  const norm = plan.toLowerCase();
  if (norm.includes('year') || norm.includes('annual')) return 'Yearly · all features';
  if (norm.includes('month')) return 'Monthly · all features';
  if (norm.includes('life')) return 'Lifetime · all features';
  return `${plan} · all features`;
}

export default function PremiumCelebrationGate() {
  const { isLoaded, isSignedIn, user } = useUser();
  const [show, setShow] = useState(false);
  const [status, setStatus] = useState<SubscriptionStatus | null>(null);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    let cancelled = false;

    (async () => {
      try {
        const [subRes, welcomeRes] = await Promise.all([
          fetch('/api/subscription/status'),
          fetch('/api/premium-welcome'),
        ]);
        if (!subRes.ok || !welcomeRes.ok) return;

        const sub: SubscriptionStatus = await subRes.json();
        const welcome: { seen?: boolean } = await welcomeRes.json();

        if (cancelled) return;
        if (sub.active === true && welcome.seen !== true) {
          setStatus(sub);
          setShow(true);
        }
      } catch {
        // Fail-safe: never block the app on an error.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn]);

  if (!show || !status) return null;

  const email = user?.primaryEmailAddress?.emailAddress ?? '';

  const handleDismiss = () => {
    setShow(false);
    // Best-effort persist; nothing to do if it fails — the flag just stays
    // unset and the ceremony can replay on a later load (never blocks).
    fetch('/api/premium-welcome', { method: 'POST' }).catch(() => {});
  };

  return (
    <PremiumCelebration
      email={email}
      planLabel={planLabel(status.plan)}
      accessUntil={status.currentPeriodEnd ?? null}
      onDismiss={handleDismiss}
    />
  );
}
