'use client';

import { useUser, SignInButton, SignUpButton } from '@clerk/nextjs';
import { useEffect } from 'react';

import { BrandPreviewPanel } from '@/components/school-onboarding/BrandPreviewPanel';
import { SchoolOnboardingShell } from '@/components/school-onboarding/SchoolOnboardingShell';
import { useWizard } from '@/components/school-onboarding/WizardState';

export default function StepAccount() {
  const { isSignedIn, user } = useUser();
  const { payload, update } = useWizard();

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
        title="You're 4 minutes away from a branded chess platform."
        subtitle="Create your Chesster account to begin."
        canAdvance={false}
        preview={<BrandPreviewPanel payload={payload} />}
      >
        <div className="flex flex-col gap-3">
          <SignUpButton mode="modal">
            <button className="rounded-lg bg-blue-600 px-4 py-2.5 text-white font-medium hover:bg-blue-700">
              Sign up with email or Google
            </button>
          </SignUpButton>
          <SignInButton mode="modal">
            <button className="rounded-lg border border-gray-300 px-4 py-2.5 text-gray-700 hover:bg-gray-50">
              I already have an account
            </button>
          </SignInButton>
          <p className="text-xs text-gray-500 mt-2">
            We never sell your data. 30-day money-back guarantee.
          </p>
        </div>
      </SchoolOnboardingShell>
    );
  }

  return (
    <SchoolOnboardingShell
      step="account"
      title={`Welcome${payload.full_name ? `, ${payload.full_name.split(' ')[0]}` : ''}.`}
      subtitle="Tell us a bit about you so support can reach out when needed."
      preview={<BrandPreviewPanel payload={payload} />}
      canAdvance={Boolean(payload.full_name)}
    >
      <div className="flex flex-col gap-4">
        <label className="block">
          <span className="text-sm font-medium text-gray-700">Full name</span>
          <input
            type="text"
            value={payload.full_name || ''}
            onChange={e => update({ full_name: e.target.value })}
            placeholder="Dinara Aitkulova"
            className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 outline-none"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-gray-700">
            Phone <span className="text-gray-400">(optional)</span>
          </span>
          <input
            type="tel"
            value={payload.phone || ''}
            onChange={e => update({ phone: e.target.value })}
            placeholder="+7 700 000 0000"
            className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 outline-none"
          />
          <p className="mt-1 text-xs text-gray-500">
            Only used by support for WhatsApp activation in Kazakhstan.
          </p>
        </label>
      </div>
    </SchoolOnboardingShell>
  );
}
