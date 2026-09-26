'use client';

/**
 * Shared subscription plan picker for the restricted-member upgrade pages
 * (`/upgrade/expired`, `/upgrade/continue`). Weekly / monthly / yearly with the
 * yearly plan visually highlighted; one dominant CTA that checks out the
 * selected plan via the existing `/api/whop/checkout` route (same contract as
 * onboarding) and redirects to the returned Whop URL. Plan ids come from the
 * `NEXT_PUBLIC_WHOP_*` env vars, prices from the `access.upgrade` messages.
 */
import { useState } from 'react';
import { useTranslations } from 'next-intl';

type PlanKey = 'weekly' | 'monthly' | 'yearly';

const PLAN_IDS: Record<PlanKey, string | undefined> = {
  weekly: process.env.NEXT_PUBLIC_WHOP_WEEKLY_PLAN,
  monthly: process.env.NEXT_PUBLIC_WHOP_MONTHLY_PLAN,
  yearly: process.env.NEXT_PUBLIC_WHOP_YEARLY_PLAN,
};

const PLAN_KEYS: PlanKey[] = ['weekly', 'monthly', 'yearly'];

export default function PlanPicker() {
  const t = useTranslations('access');
  const [selected, setSelected] = useState<PlanKey>('yearly');
  const [loading, setLoading] = useState(false);

  const handleSubscribe = async () => {
    const planId = PLAN_IDS[selected];
    if (!planId || loading) return;
    setLoading(true);
    try {
      const res = await fetch('/api/whop/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ planId }),
      });
      const data = await res.json();
      if (data.checkoutUrl) {
        window.location.href = data.checkoutUrl;
        return;
      }
      setLoading(false);
    } catch (err) {
      console.error('[upgrade] checkout error', err);
      setLoading(false);
    }
  };

  return (
    <div className="w-full space-y-4">
      <div className="flex flex-col gap-3">
        {PLAN_KEYS.map((key) => {
          const isSelected = selected === key;
          const isYearly = key === 'yearly';
          return (
            <button
              key={key}
              type="button"
              onClick={() => setSelected(key)}
              aria-pressed={isSelected}
              className={`relative flex items-center justify-between rounded-2xl border-2 p-4 text-left transition-all ${
                isYearly
                  ? isSelected
                    ? 'border-purple-500 bg-purple-50 scale-[1.02] shadow-md'
                    : 'border-purple-300 bg-purple-50/50'
                  : isSelected
                    ? 'border-purple-400 bg-white shadow-sm'
                    : 'border-gray-200 bg-white'
              }`}
            >
              {isYearly && (
                <span className="absolute -top-2.5 right-4 rounded-full bg-green-500 px-2.5 py-0.5 text-[10px] font-bold text-white">
                  {t('upgrade.bestValue')}
                </span>
              )}
              <div>
                <div className="font-bold text-gray-900">
                  {t(`upgrade.${key}`)}
                </div>
                {isYearly && (
                  <div className="mt-0.5 text-xs font-medium text-green-600">
                    {t('upgrade.perMonth')}
                  </div>
                )}
              </div>
              <div className="font-bold text-gray-900">
                {t(`upgrade.${key}Price`)}
              </div>
            </button>
          );
        })}
      </div>

      <button
        type="button"
        onClick={handleSubscribe}
        disabled={loading}
        className={`w-full rounded-full bg-purple-600 px-6 py-4 text-lg font-bold text-white shadow-lg transition-transform hover:scale-105 active:scale-95 ${
          loading ? 'cursor-wait opacity-60' : ''
        }`}
      >
        {loading
          ? t('upgrade.loading')
          : selected === 'yearly'
            ? t('upgrade.startYearly')
            : t('upgrade.subscribe')}
      </button>
    </div>
  );
}
