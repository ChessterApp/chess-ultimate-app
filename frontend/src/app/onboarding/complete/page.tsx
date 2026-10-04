'use client';

import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useUser } from '@clerk/nextjs';
import { useTranslations } from 'next-intl';
import {
  readPendingAnswers,
  clearPendingAnswers,
  type PendingOnboardingAnswers,
} from '@/lib/onboarding/pendingAnswers';

/**
 * Post-signup claim page. A new consumer account lands here (Clerk
 * `redirect_url=/onboarding/complete`), where the anonymous funnel answers are
 * attached to the account, then we route to /learn.
 *
 * Answer source: localStorage (primary) → Clerk `unsafeMetadata.onboardingAnswers`
 * (backup, written on the sign-up page) if localStorage was cleared. The POST is
 * best-effort — a failure just means plain progressive unlock, never a dead end.
 */
export default function OnboardingCompletePage() {
  const t = useTranslations('onboarding.complete');
  const router = useRouter();
  const { isLoaded, isSignedIn, user } = useUser();
  const ranRef = useRef(false);

  useEffect(() => {
    if (!isLoaded || ranRef.current) return;
    ranRef.current = true;

    if (!isSignedIn) {
      router.replace('/sign-in');
      return;
    }

    (async () => {
      let answers: PendingOnboardingAnswers | null = readPendingAnswers();
      if (!answers) {
        const carried = (user?.unsafeMetadata as Record<string, unknown> | undefined)
          ?.onboardingAnswers;
        if (carried && typeof carried === 'object') {
          answers = carried as PendingOnboardingAnswers;
        }
      }

      if (answers) {
        try {
          await fetch('/api/onboarding/profile', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(answers),
          });
        } catch {
          /* best-effort — progressive unlock still works without it */
        }
      }

      clearPendingAnswers();
      router.replace('/learn');
    })();
  }, [isLoaded, isSignedIn, user, router]);

  return (
    <div className="flex-1 flex min-h-screen flex-col items-center justify-center gap-6 px-6 text-center">
      <div className="w-10 h-10 border-4 border-white/30 border-t-white rounded-full animate-spin" />
      <div className="space-y-1">
        <h1 className="text-xl font-bold text-white">{t('title')}</h1>
        <p className="text-white/70 text-sm">{t('subtitle')}</p>
      </div>
    </div>
  );
}
