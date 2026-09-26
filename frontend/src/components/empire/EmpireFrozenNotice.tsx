'use client';

/**
 * "Membership paused" notice for a frozen Chess Empire member.
 *
 * Rendered when `getMembershipState` returns `frozen` — the school's nightly
 * sync set `link_status = 'frozen'`. Unlike `no_link`, this is NOT recoverable
 * by re-claiming the invite, so there is deliberately NO claim/retry button:
 * only the branch/school administrator can reactivate the membership. Copy
 * points the user there. Styled after `EmpireAccessExpired` so it matches the
 * other empire full-screen states.
 */
import { useTranslations } from 'next-intl';

export default function EmpireFrozenNotice() {
  const t = useTranslations('empire');
  return (
    <div
      data-testid="empire-home-frozen"
      className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4 text-center"
    >
      <div className="w-full max-w-md rounded-3xl bg-white p-8 shadow-xl">
        <h1 className="text-2xl font-bold text-gray-800">{t('frozenTitle')}</h1>
        <p className="mt-3 text-sm text-gray-500">{t('frozenBody')}</p>
        <p className="mt-4 text-sm font-medium text-gray-600">
          {t('frozenContact')}
        </p>
      </div>
    </div>
  );
}
