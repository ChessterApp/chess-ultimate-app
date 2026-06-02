'use client';

import Link from 'next/link';

import { useWizard } from '@/components/school-onboarding/WizardState';

export default function StepDone() {
  const { payload } = useWizard();
  const slug = payload.slug || 'yourschool';
  const tier = payload.tier
    ? payload.tier.charAt(0).toUpperCase() + payload.tier.slice(1)
    : 'Starter';
  const invitedCount = (payload.invites || []).length;

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-white flex items-center justify-center px-6 py-20">
      <div className="max-w-lg w-full bg-white rounded-2xl border border-gray-200 shadow-sm p-8 text-center">
        <div className="text-4xl">🎉</div>
        <h1 className="mt-4 text-2xl font-bold">
          {payload.school_name || 'Your school'} is live.
        </h1>
        <dl className="mt-6 grid grid-cols-2 gap-4 text-sm text-left">
          <div>
            <dt className="text-gray-500">Your platform</dt>
            <dd className="font-mono">{slug}.chesster.io</dd>
          </div>
          <div>
            <dt className="text-gray-500">Plan</dt>
            <dd>{tier} · {payload.billing_cycle || 'monthly'}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Students invited</dt>
            <dd>{invitedCount}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Admin</dt>
            <dd>
              <a
                href={`https://${slug}.chesster.io/admin`}
                className="text-blue-600 hover:underline"
              >
                {slug}.chesster.io/admin
              </a>
            </dd>
          </div>
        </dl>
        <Link
          href={`https://${slug}.chesster.io/admin`}
          className="mt-6 inline-flex items-center justify-center rounded-lg bg-blue-600 px-5 py-3 text-white font-semibold hover:bg-blue-700"
        >
          Take me to my dashboard →
        </Link>
        <p className="mt-4 text-xs text-gray-500">
          Bookmark this page. Need help? Email{' '}
          <a href="mailto:support@chesster.io" className="underline">
            support@chesster.io
          </a>
          .
        </p>
      </div>
    </div>
  );
}
