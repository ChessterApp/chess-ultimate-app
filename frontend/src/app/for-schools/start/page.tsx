'use client';

import { useUser, SignInButton, SignUpButton } from '@clerk/nextjs';
import { useEffect } from 'react';
import { useTranslations } from 'next-intl';

import { BrandPreviewPanel } from '@/components/school-onboarding/BrandPreviewPanel';
import { SchoolOnboardingShell } from '@/components/school-onboarding/SchoolOnboardingShell';
import { useWizard } from '@/components/school-onboarding/WizardState';

export default function StepAccount() {
  const { isSignedIn, user } = useUser();
  const { payload, update } = useWizard();
  const t = useTranslations('schoolOnboarding.account');

  useEffect(() => {
    if (isSignedIn && user) {
      const email = user.primaryEmailAddress?.emailAddress;
      const fullName = user.fullName || user.firstName || '';
      if (email && payload.email !== email) update({ email });
      if (fullName && !payload.full_name) update({ full_name: fullName });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSignedIn, user?.id]);

  if (!isSignedIn) {
    return (
      <SchoolOnboardingShell
        step="account"
        title={t('notSignedInTitle')}
        subtitle={t('notSignedInSubtitle')}
        canAdvance={false}
        preview={<BrandPreviewPanel payload={payload} />}
      >
        <div className="flex flex-col gap-3">
          <SignUpButton mode="modal">
            <button className="rounded-lg bg-blue-600 px-4 py-2.5 text-white font-medium hover:bg-blue-700">
              {t('signUpButton')}
            </button>
          </SignUpButton>
          <SignInButton mode="modal">
            <button className="rounded-lg border border-gray-300 px-4 py-2.5 text-gray-700 hover:bg-gray-50">
              {t('alreadyHaveAccount')}
            </button>
          </SignInButton>
          <p className="text-xs text-gray-500 mt-2">{t('reassurance')}</p>
        </div>
      </SchoolOnboardingShell>
    );
  }

  const firstName = payload.full_name ? payload.full_name.split(' ')[0] : '';
  const title = firstName
    ? t('signedInTitleNamed', { firstName })
    : t('signedInTitlePlain');

  return (
    <SchoolOnboardingShell
      step="account"
      title={title}
      subtitle={t('signedInSubtitle')}
      preview={<BrandPreviewPanel payload={payload} />}
      canAdvance={Boolean(payload.full_name)}
    >
      <div className="flex flex-col gap-4">
        <label className="block">
          <span className="text-sm font-medium text-gray-700">{t('fullNameLabel')}</span>
          <input
            type="text"
            value={payload.full_name || ''}
            onChange={e => update({ full_name: e.target.value })}
            placeholder={t('fullNamePlaceholder')}
            className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 outline-none"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-gray-700">
            {t('phoneLabel')} <span className="text-gray-400">{t('phoneOptional')}</span>
          </span>
          <input
            type="tel"
            value={payload.phone || ''}
            onChange={e => update({ phone: e.target.value })}
            placeholder={t('phonePlaceholder')}
            className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 outline-none"
          />
          <p className="mt-1 text-xs text-gray-500">{t('phoneHelp')}</p>
        </label>
      </div>
    </SchoolOnboardingShell>
  );
}
