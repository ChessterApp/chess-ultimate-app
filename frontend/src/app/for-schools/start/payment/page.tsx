'use client';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { BrandPreviewPanel } from '@/components/school-onboarding/BrandPreviewPanel';
import { SchoolOnboardingShell } from '@/components/school-onboarding/SchoolOnboardingShell';
import { useWizard } from '@/components/school-onboarding/WizardState';

export default function StepPayment() {
  const { payload, update, setStep } = useWizard();
  const t = useTranslations('schoolOnboarding.payment');
  const router = useRouter();
  const params = useSearchParams();
  const paidParam = params?.get('status') === 'paid';
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [promoCode, setPromoCode] = useState('');
  const [applyingPromo, setApplyingPromo] = useState(false);
  const [promoError, setPromoError] = useState<string | null>(null);

  const tier = payload.tier || 'growth';
  const cycle = payload.billing_cycle || 'monthly';

  async function ensureOrg(): Promise<string | null> {
    let orgId = payload.organization_id;
    if (orgId) return orgId;
    const orgRes = await fetch('/api/onboarding/create-org', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: payload.school_name,
        slug: payload.slug,
        contact_email: payload.email,
      }),
    });
    const orgBody = await orgRes.json();
    if (!orgRes.ok) {
      setError(orgBody.error || t('couldNotCreateOrg'));
      return null;
    }
    orgId = orgBody.organization.id;
    update({ organization_id: orgId });
    return orgId ?? null;
  }

  async function ensureOrgThenCheckout() {
    setError(null);
    setCreating(true);
    try {
      const orgId = await ensureOrg();
      if (!orgId) return;

      const ckRes = await fetch('/api/whop/org-checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tier,
          billing_cycle: cycle,
          org_id: orgId,
        }),
      });
      const ck = await ckRes.json();
      if (!ckRes.ok) {
        setError(ck.error || t('checkoutFailed'));
        return;
      }
      window.location.href = ck.checkoutUrl;
    } catch (e) {
      setError((e as Error).message || t('unexpectedError'));
    } finally {
      setCreating(false);
    }
  }

  async function applyPromo() {
    const code = promoCode.trim();
    if (!code) return;
    setPromoError(null);
    setError(null);
    setApplyingPromo(true);
    try {
      const orgId = await ensureOrg();
      if (!orgId) return;

      const res = await fetch('/api/promo/redeem', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, orgId, tier, cycle }),
      });
      const data = await res.json();
      if (!res.ok) {
        const code = typeof data?.error === 'string' ? data.error : 'generic';
        const known = new Set([
          'not_found',
          'inactive',
          'expired',
          'code_exhausted',
          'partial_discount_unsupported',
          'forbidden',
          'unauthorized',
        ]);
        setPromoError(t(`promoErrors.${known.has(code) ? code : 'generic'}`));
        return;
      }
      update({ payment_status: 'paid' });
      setStep('brand');
      router.push(data.redirect);
    } catch (e) {
      setPromoError((e as Error).message || t('unexpectedError'));
    } finally {
      setApplyingPromo(false);
    }
  }

  const isPaid = paidParam || payload.payment_status === 'paid';

  return (
    <SchoolOnboardingShell
      step="payment"
      title={isPaid ? t('titlePaid') : t('titleUnpaid')}
      subtitle={isPaid ? t('subtitlePaid') : t('subtitleUnpaid')}
      backTo="/for-schools/start/plan"
      canAdvance={isPaid}
      preview={<BrandPreviewPanel payload={payload} />}
      nextLabel={isPaid ? t('nextLabelPaid') : undefined}
    >
      <div className="flex flex-col gap-4">
        <div className="rounded-xl border border-gray-200 p-4 bg-gray-50">
          <div className="text-xs uppercase tracking-wide text-gray-500">
            {t('signingUpFor')}
          </div>
          <div className="mt-1 font-semibold text-gray-900">
            {tier.charAt(0).toUpperCase() + tier.slice(1)} · {cycle}
          </div>
          <div className="mt-1 text-sm text-gray-600">
            {payload.school_name || t('yourSchoolFallback')} ·{' '}
            <span className="font-mono">{payload.slug || t('slugFallback')}.chesster.io</span>
          </div>
        </div>

        {!isPaid && (
          <>
            <div className="rounded-xl border border-gray-200 p-4">
              <label htmlFor="promo-code" className="block text-sm font-semibold text-gray-900">
                {t('promoHeading')}
              </label>
              <div className="mt-2 flex gap-2">
                <input
                  id="promo-code"
                  type="text"
                  value={promoCode}
                  onChange={e => setPromoCode(e.target.value)}
                  disabled={applyingPromo}
                  placeholder={t('promoPlaceholder')}
                  className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none disabled:bg-gray-100"
                />
                <button
                  type="button"
                  onClick={applyPromo}
                  disabled={applyingPromo || !promoCode.trim()}
                  className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:bg-gray-300"
                >
                  {applyingPromo ? t('promoApplying') : t('promoApply')}
                </button>
              </div>
              {promoError && <p className="mt-2 text-sm text-red-600">{promoError}</p>}
            </div>

            <button
              type="button"
              onClick={ensureOrgThenCheckout}
              disabled={creating}
              className="rounded-lg bg-blue-600 px-4 py-2.5 text-white font-medium hover:bg-blue-700 disabled:bg-gray-300"
            >
              {creating ? t('preparingCheckout') : t('payWithWhop')}
            </button>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <p className="text-xs text-gray-500">{t('guarantee')}</p>
          </>
        )}

        {isPaid && (
          <button
            type="button"
            onClick={() => update({ payment_status: 'paid' })}
            className="rounded-lg border border-green-600 bg-green-50 px-4 py-2.5 text-green-800 font-medium"
          >
            {t('paymentReceived')}
          </button>
        )}
      </div>
    </SchoolOnboardingShell>
  );
}
