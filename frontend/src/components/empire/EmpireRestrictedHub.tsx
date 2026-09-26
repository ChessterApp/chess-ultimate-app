'use client';

/**
 * Home "hub" for a restricted Chess Empire member — `frozen` (school paused the
 * membership) or `expired` (online trial ended). Replaces the old dead-end
 * notice: it states the status honestly, points to what's still open (Learn),
 * and offers the audience-specific upgrade path. Rendered by
 * `empire-homepage-render` for both restricted states.
 */
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { getAccessPolicy } from '@/lib/access-policy';

export default function EmpireRestrictedHub({
  reason,
}: {
  reason: 'frozen' | 'expired';
}) {
  const t = useTranslations('access');
  const policy = getAccessPolicy(reason);
  const isFrozen = reason === 'frozen';

  return (
    <div
      data-testid={isFrozen ? 'empire-home-frozen' : 'empire-home-expired'}
      className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4 py-10 text-center"
    >
      <div className="w-full max-w-md space-y-6">
        {/* Status */}
        <div className="rounded-3xl bg-white p-8 shadow-xl">
          <h1 className="text-2xl font-bold text-gray-800">
            {t(isFrozen ? 'hub.frozenTitle' : 'hub.expiredTitle')}
          </h1>
          <p className="mt-3 text-sm text-gray-500">
            {t(isFrozen ? 'hub.frozenStatus' : 'hub.expiredStatus')}
          </p>
        </div>

        {/* What's still open */}
        <div className="rounded-3xl bg-white p-6 text-left shadow-sm">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
            {t('hub.stillOpenTitle')}
          </h2>
          <p className="mt-2 text-sm text-gray-600">{t('hub.learnStillOpen')}</p>
          {/* TODO(Phase 2): show "finish Level N — X%" progress here (needs the
              level-progress fetch — intentionally not fetched in Phase 1). */}
          <Link
            href="/learn"
            className="mt-4 inline-flex items-center justify-center rounded-full bg-gray-900 px-5 py-2.5 text-sm font-semibold text-white transition-transform hover:scale-105 active:scale-95"
          >
            {t('hub.continueLearning')}
          </Link>
        </div>

        {/* Upgrade CTA */}
        <div className="space-y-3">
          <Link
            href={policy.upgradePath}
            className="inline-flex w-full items-center justify-center rounded-full bg-purple-600 px-6 py-3 text-base font-bold text-white shadow-lg transition-transform hover:scale-105 active:scale-95"
          >
            {t(isFrozen ? 'continueCta' : 'keepGoingCta')}
          </Link>
          {isFrozen && (
            <p className="text-xs text-gray-400">{t('hub.contactSchool')}</p>
          )}
        </div>
      </div>
    </div>
  );
}
