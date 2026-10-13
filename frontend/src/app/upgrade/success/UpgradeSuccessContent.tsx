'use client';

/**
 * Whop checkout return page. The webhook that activates the subscription can
 * lag the redirect, so poll the status API (see `pollSubscription`) and show
 * loading → success (auto-redirect to /learn) or a reassuring timeout state.
 */
import { useEffect, useRef } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { ANALYTICS_EVENTS, track } from '@/lib/analytics/events';
import { useSubscriptionActivation } from './pollSubscription';

export const SUCCESS_REDIRECT_MS = 5000;
const KNOWN_PLANS = new Set(['weekly', 'monthly', 'yearly']);

export default function UpgradeSuccessContent() {
  const t = useTranslations('upgradeSuccess');
  const router = useRouter();
  const { state, retry } = useSubscriptionActivation();
  const viewedRef = useRef(false);
  const activatedRef = useRef(false);

  useEffect(() => {
    if (viewedRef.current) return;
    viewedRef.current = true;
    track(ANALYTICS_EVENTS.CHECKOUT_RETURN_VIEWED);
  }, []);

  useEffect(() => {
    if (state.phase !== 'success') return;
    if (!activatedRef.current) {
      activatedRef.current = true;
      track(ANALYTICS_EVENTS.SUBSCRIPTION_ACTIVATED_CLIENT, { tier: state.plan });
    }
    const timer = setTimeout(() => router.push('/learn'), SUCCESS_REDIRECT_MS);
    return () => clearTimeout(timer);
  }, [state, router]);

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center gap-6 px-4 py-10 text-center">
      {state.phase === 'loading' && (
        <div role="status" className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-purple-200 border-t-purple-600" />
          <h1 className="text-2xl font-bold text-gray-900">{t('loadingTitle')}</h1>
          <p className="text-sm text-gray-500">{t('loadingBody')}</p>
        </div>
      )}

      {state.phase === 'success' && (
        <>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{t('successTitle')}</h1>
            <p className="mt-2 text-sm text-gray-500">
              {state.plan && KNOWN_PLANS.has(state.plan)
                ? t('successPlan', { plan: t(`plans.${state.plan}`) })
                : t('successBody')}
            </p>
          </div>
          <Link
            href="/learn"
            className="w-full rounded-full bg-purple-600 px-6 py-4 text-lg font-bold text-white shadow-lg transition-transform hover:scale-105 active:scale-95"
          >
            {t('startLearning')}
          </Link>
          <p className="text-xs text-gray-400">{t('redirecting')}</p>
        </>
      )}

      {state.phase === 'timeout' && (
        <>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{t('timeoutTitle')}</h1>
            <p className="mt-2 text-sm text-gray-500">{t('timeoutBody')}</p>
          </div>
          <button
            type="button"
            onClick={retry}
            className="w-full rounded-full bg-purple-600 px-6 py-4 text-lg font-bold text-white shadow-lg transition-transform hover:scale-105 active:scale-95"
          >
            {t('retry')}
          </button>
          <p className="text-sm text-gray-500">
            {t('supportPrompt')}{' '}
            <a href="mailto:support@chesster.io" className="font-semibold text-purple-600 underline">
              support@chesster.io
            </a>
          </p>
        </>
      )}
    </div>
  );
}
