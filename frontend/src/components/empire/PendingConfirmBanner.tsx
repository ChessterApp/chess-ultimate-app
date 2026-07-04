'use client';

/**
 * Client island rendered on the CE homepage when the user's link_status is
 * `pending_confirm` (email auto-match). Confirm → POST /confirm, page
 * refreshes into `verified` state. Reject → POST /reject, page reloads into
 * `no_link` state.
 */
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';

interface PendingConfirmBannerProps {
  displayName: string;
}

export default function PendingConfirmBanner({
  displayName,
}: PendingConfirmBannerProps) {
  const t = useTranslations('empire');
  const router = useRouter();
  const [busy, setBusy] = useState<'confirm' | 'reject' | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function post(kind: 'confirm' | 'reject') {
    setBusy(kind);
    setError(null);
    try {
      const res = await fetch(`/api/chess-empire/link/${kind}`, {
        method: 'POST',
      });
      if (!res.ok) {
        setError('error');
        setBusy(null);
        return;
      }
      router.refresh();
    } catch {
      setError('error');
      setBusy(null);
    }
  }

  return (
    <section
      data-testid="empire-pending-confirm"
      className="rounded-2xl border bg-amber-50 dark:bg-amber-900/20 p-5 md:p-6 shadow-sm flex flex-col gap-3"
      style={{ borderColor: 'var(--brand-primary, #f59e0b)' }}
    >
      <h2 className="text-xl font-semibold text-amber-900 dark:text-amber-100">
        {t('pendingConfirmTitle', { name: displayName })}
      </h2>
      <p className="text-sm text-amber-900/80 dark:text-amber-100/80">
        {t('pendingConfirmSubtitle')}
      </p>
      <div className="flex flex-wrap gap-2 pt-1">
        <button
          type="button"
          data-testid="empire-pending-confirm-yes"
          onClick={() => post('confirm')}
          disabled={busy !== null}
          className="px-4 py-2 rounded-lg font-medium text-white shadow-sm disabled:opacity-60"
          style={{ backgroundColor: 'var(--brand-primary, #1a73e8)' }}
        >
          {busy === 'confirm'
            ? t('pendingConfirmSubmitting')
            : t('pendingConfirmYes')}
        </button>
        <button
          type="button"
          data-testid="empire-pending-confirm-no"
          onClick={() => post('reject')}
          disabled={busy !== null}
          className="px-4 py-2 rounded-lg font-medium border border-amber-300 text-amber-900 dark:text-amber-100 disabled:opacity-60"
        >
          {busy === 'reject'
            ? t('rejectSubmitting')
            : t('pendingConfirmNo')}
        </button>
      </div>
      {error && (
        <p className="text-sm text-red-700" data-testid="empire-pending-error">
          {error}
        </p>
      )}
    </section>
  );
}
