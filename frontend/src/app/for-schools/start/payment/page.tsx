'use client';

import { useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { BrandPreviewPanel } from '@/components/school-onboarding/BrandPreviewPanel';
import { SchoolOnboardingShell } from '@/components/school-onboarding/SchoolOnboardingShell';
import { useWizard } from '@/components/school-onboarding/WizardState';

export default function StepPayment() {
  const { payload, update } = useWizard();
  const t = useTranslations('schoolOnboarding.payment');
  const params = useSearchParams();
  const paidParam = params?.get('status') === 'paid';
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tier = payload.tier || 'growth';
  const cycle = payload.billing_cycle || 'monthly';

  async function ensureOrgThenCheckout() {
    setError(null);
    setCreating(true);
    try {
      let orgId = payload.organization_id;
      if (!orgId) {
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
          return;
        }
        orgId = orgBody.organization.id;
        update({ organization_id: orgId });
      }

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
