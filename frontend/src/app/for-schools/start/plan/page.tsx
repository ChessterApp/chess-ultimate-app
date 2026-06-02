'use client';

import { useEffect, useState } from 'react';

import { BrandPreviewPanel } from '@/components/school-onboarding/BrandPreviewPanel';
import { SchoolOnboardingShell } from '@/components/school-onboarding/SchoolOnboardingShell';
import { useWizard } from '@/components/school-onboarding/WizardState';
import {
  fetchTiers,
  recommendTier,
  tierOrder,
  type Tier,
  type TierId,
  type TierMap,
} from '@/lib/tiers';

function priceLabel(tier: Tier, cycle: 'monthly' | 'annual'): string {
  if (tier.price_usd_monthly === null) return 'Custom';
  const amt = cycle === 'monthly' ? tier.price_usd_monthly : tier.price_usd_annual;
  if (amt === null) return 'Custom';
  return cycle === 'monthly' ? `$${amt}/mo` : `$${amt}/yr`;
}

export default function StepPlan() {
  const { payload, update } = useWizard();
  const [tiers, setTiers] = useState<TierMap | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchTiers()
      .then(setTiers)
      .catch(err => setError(err.message || 'Failed to load tiers'));
  }, []);

  const studentEstimate = payload.student_count_estimate ?? 50;
  const selectedTier = payload.tier as TierId | undefined;
  const cycle = payload.billing_cycle ?? 'monthly';
  const recommended = tiers ? recommendTier(studentEstimate, tiers) : null;

  const canAdvance = Boolean(selectedTier && selectedTier !== 'enterprise');

  return (
    <SchoolOnboardingShell
      step="plan"
      title="Pick a plan that fits your school."
      subtitle="Anchored to how many students you'll have. 30-day money-back guarantee."
      backTo="/for-schools/start/school"
      canAdvance={canAdvance}
      preview={<BrandPreviewPanel payload={payload} />}
    >
      <div className="flex flex-col gap-5">
        <div>
          <label className="text-sm font-medium text-gray-700">
            How many students will you have on Chesster?
          </label>
          <div className="mt-2 flex items-center gap-3">
            <input
              type="range"
              min={1}
              max={500}
              step={1}
              value={studentEstimate}
              onChange={e =>
                update({ student_count_estimate: Number(e.target.value) })
              }
              className="flex-1 accent-blue-600"
            />
            <span className="w-16 text-right font-semibold tabular-nums">
              {studentEstimate}+
            </span>
          </div>
          {recommended && (
            <p className="mt-2 text-xs text-blue-700">
              ✨ We recommend <strong>{tiers?.[recommended].display_name}</strong>.
            </p>
          )}
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => update({ billing_cycle: 'monthly' })}
            className={`px-3 py-1.5 text-sm rounded-full border ${
              cycle === 'monthly'
                ? 'bg-gray-900 text-white border-gray-900'
                : 'bg-white text-gray-700 border-gray-300'
            }`}
          >
            Monthly
          </button>
          <button
            type="button"
            onClick={() => update({ billing_cycle: 'annual' })}
            className={`px-3 py-1.5 text-sm rounded-full border ${
              cycle === 'annual'
                ? 'bg-gray-900 text-white border-gray-900'
                : 'bg-white text-gray-700 border-gray-300'
            }`}
          >
            Annual <span className="ml-1 text-green-500">−15%</span>
          </button>
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {tiers &&
            tierOrder().map(id => {
              const tier = tiers[id];
              if (!tier) return null;
              const isSelected = selectedTier === id;
              const isRecommended = recommended === id;
              const isEnterprise = id === 'enterprise';

              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => update({ tier: id })}
                  className={`text-left rounded-xl border p-4 transition-colors ${
                    isSelected
                      ? 'border-blue-600 ring-2 ring-blue-200 bg-blue-50/30'
                      : isRecommended
                      ? 'border-blue-300'
                      : 'border-gray-200'
                  } hover:border-gray-400`}
                >
                  <div className="flex items-baseline justify-between">
                    <span className="font-semibold">{tier.display_name}</span>
                    {isRecommended && (
                      <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-blue-600 text-white">
                        Most popular
                      </span>
                    )}
                  </div>
                  <div className="mt-1 text-xl font-bold">
                    {priceLabel(tier, cycle)}
                  </div>
                  <div className="mt-0.5 text-xs text-gray-500">
                    {tier.seat_cap === null
                      ? 'Unlimited students'
                      : `Up to ${tier.seat_cap} students`}
                  </div>
                  <ul className="mt-2 space-y-0.5">
                    {tier.features.slice(0, 4).map(f => (
                      <li key={f} className="text-xs text-gray-600">
                        ✓ {f}
                      </li>
                    ))}
                  </ul>
                  {isEnterprise && (
                    <p className="mt-2 text-xs text-gray-500">
                      Talk to sales — we&apos;ll send a Calendly link.
                    </p>
                  )}
                </button>
              );
            })}
        </div>
      </div>
    </SchoolOnboardingShell>
  );
}
