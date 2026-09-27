'use client';

/**
 * Client body for the upgrade pages, shared by `/upgrade/expired` (trial-ended
 * audience) and `/upgrade/continue` (frozen school-student audience). Same plan
 * picker + checkout flow; the `continue` audience additionally gets a "contact
 * your school" block. Copy is audience-specific so neither reads like a generic
 * trial upsell.
 */
import { useTranslations } from 'next-intl';
import PlanPicker from '@/components/access/PlanPicker';

export default function UpgradeContent({
  audience,
}: {
  audience: 'expired' | 'continue';
}) {
  const t = useTranslations('access');
  const isContinue = audience === 'continue';

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center gap-6 px-4 py-10">
      <div className="text-center">
        <h1 className="text-2xl font-bold text-gray-900">
          {t(isContinue ? 'upgrade.continueHeadline' : 'upgrade.expiredHeadline')}
        </h1>
        <p className="mt-2 text-sm text-gray-500">
          {t(isContinue ? 'upgrade.continueSubtitle' : 'upgrade.expiredSubtitle')}
        </p>
      </div>

      <PlanPicker />

      {isContinue && (
        <div className="rounded-2xl border border-gray-200 bg-gray-50 p-5 text-left">
          <h2 className="text-sm font-semibold text-gray-800">
            {t('upgrade.contactSchoolTitle')}
          </h2>
          <p className="mt-1 text-sm text-gray-500">
            {t('upgrade.contactSchoolBody')}
          </p>
        </div>
      )}
    </div>
  );
}
