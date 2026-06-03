'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';

import { BrandPreviewPanel } from '@/components/school-onboarding/BrandPreviewPanel';
import { SchoolOnboardingShell } from '@/components/school-onboarding/SchoolOnboardingShell';
import { useWizard } from '@/components/school-onboarding/WizardState';
import { CsvImporter } from '@/components/school-onboarding/CsvImporter';
import { LoomEmbed } from '@/components/support/LoomEmbed';
import { ANALYTICS_EVENTS, track } from '@/lib/analytics/events';
import { buildLoomConfig, pickLoomForTier } from '@/lib/loom';

interface InviteRow {
  email: string;
  first_name?: string;
  role: 'student' | 'teacher' | 'admin';
}

interface SendResult {
  email: string;
  status: 'sent' | 'failed' | 'over_limit';
  reason?: string;
}

function parseList(raw: string): InviteRow[] {
  return raw
    .split(/[\s,;\n]+/)
    .map(s => s.trim())
    .filter(s => /^.+@.+\..+$/.test(s))
    .map(email => ({ email, role: 'student' as const }));
}

export default function StepInvite() {
  const { payload, update } = useWizard();
  const t = useTranslations('schoolOnboarding.invite');
  const [bulkText, setBulkText] = useState('');
  const [rows, setRows] = useState<InviteRow[]>(payload.invites as InviteRow[] || []);
  const [sending, setSending] = useState(false);
  const [results, setResults] = useState<SendResult[]>([]);
  const [tierError, setTierError] = useState<string | null>(null);
  const [csvImporting, setCsvImporting] = useState(false);

  async function importCsvBatch(
    accepted: Array<{ email: string; first_name?: string; last_name?: string }>,
  ) {
    if (!payload.organization_id || accepted.length === 0) return;
    setCsvImporting(true);
    try {
      const res = await fetch(
        `/api/admin/organizations/${payload.organization_id}/invites/bulk`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            invites: accepted.map(r => ({
              email: r.email,
              first_name: r.first_name,
              last_name: r.last_name,
              role: 'student',
            })),
          }),
        },
      );
      const body = await res.json().catch(() => ({}));
      const out: SendResult[] = [];
      for (const a of body.accepted || []) {
        out.push({ email: a.email, status: 'sent' });
      }
      for (const r of body.rejected || []) {
        out.push({
          email: r.email,
          status: r.reason === 'tier_cap' ? 'over_limit' : 'failed',
          reason: r.reason,
        });
      }
      setResults(prev => [...prev, ...out]);
      track(ANALYTICS_EVENTS.SCHOOL_ONBOARDING_CSV_IMPORTED, {
        accepted: out.filter(o => o.status === 'sent').length,
        rejected: out.filter(o => o.status !== 'sent').length,
      });
      if ((body.rejected || []).some((r: { reason?: string }) => r.reason === 'tier_cap')) {
        setTierError(
          t('tierCapErrorBulk', { plan: body.plan ?? '' }),
        );
      }
    } finally {
      setCsvImporting(false);
    }
  }

  function appendFromBulk() {
    const parsed = parseList(bulkText);
    if (!parsed.length) return;
    const next = [...rows, ...parsed.filter(p => !rows.some(r => r.email === p.email))];
    setRows(next);
    update({ invites: next });
    setBulkText('');
  }

  function appendOne() {
    setRows(r => {
      const next = [...r, { email: '', role: 'student' as const }];
      update({ invites: next });
      return next;
    });
  }

  function patchRow(i: number, patch: Partial<InviteRow>) {
    setRows(r => {
      const next = r.map((row, idx) => (idx === i ? { ...row, ...patch } : row));
      update({ invites: next });
      return next;
    });
  }

  function removeRow(i: number) {
    setRows(r => {
      const next = r.filter((_, idx) => idx !== i);
      update({ invites: next });
      return next;
    });
  }

  async function sendInvites() {
    if (!payload.organization_id || rows.length === 0) return;
    setSending(true);
    setTierError(null);
    const out: SendResult[] = [];
    for (const row of rows) {
      if (!/^.+@.+\..+$/.test(row.email)) {
        out.push({ email: row.email, status: 'failed', reason: t('invalidEmail') });
        continue;
      }
      try {
        const res = await fetch(
          `/api/admin/organizations/${payload.organization_id}/members/invite`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: row.email, role: row.role }),
          },
        );
        if (res.status === 402) {
          const body = await res.json();
          setTierError(
            t('tierCapErrorSingle', {
              plan: body.plan,
              current: body.current_count,
              cap: body.seat_cap,
            }),
          );
          out.push({ email: row.email, status: 'over_limit' });
          break;
        }
        if (res.ok) {
          out.push({ email: row.email, status: 'sent' });
        } else {
          const body = await res.json().catch(() => ({}));
          out.push({ email: row.email, status: 'failed', reason: body.error });
        }
      } catch {
        out.push({ email: row.email, status: 'failed', reason: t('networkError') });
      }
    }
    setResults(out);
    setSending(false);

    // Clear the pending_onboarding row after the first batch lands.
    try {
      await fetch('/api/onboarding/complete', { method: 'DELETE' });
    } catch {
      // best-effort cleanup
    }
  }

  return (
    <SchoolOnboardingShell
      step="invite"
      title={t('title')}
      subtitle={t('subtitle')}
      backTo="/for-schools/start/brand"
      preview={<BrandPreviewPanel payload={payload} />}
      nextLabel={t('nextLabel')}
      canAdvance={results.some(r => r.status === 'sent')}
    >
      <div className="flex flex-col gap-4">
        {(() => {
          const cfg = buildLoomConfig(
            process.env as Record<string, string | undefined>,
          );
          const url = pickLoomForTier(cfg, payload.tier ?? null);
          return url ? (
            <LoomEmbed
              url={url}
              title={t('loomTitle')}
            />
          ) : null;
        })()}
        <CsvImporter
          remainingSeats={null}
          existingEmails={rows.map(r => r.email).filter(Boolean)}
          onSubmit={importCsvBatch}
          submitting={csvImporting}
        />

        <div>
          <label className="text-sm font-medium text-gray-700">
            {t('pasteEmailsLabel')}
          </label>
          <textarea
            value={bulkText}
            onChange={e => setBulkText(e.target.value)}
            placeholder={t('pasteEmailsPlaceholder')}
            rows={3}
            className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-100 outline-none"
          />
          <button
            type="button"
            onClick={appendFromBulk}
            className="mt-2 text-xs rounded border border-gray-300 px-2.5 py-1 hover:bg-gray-50"
          >
            {t('addToList')}
          </button>
        </div>

        <div>
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-gray-700">
              {t('inviteesCount', { count: rows.length })}
            </label>
            <button
              type="button"
              onClick={appendOne}
              className="text-xs text-blue-600 hover:underline"
            >
              {t('addAnother')}
            </button>
          </div>
          <ul className="mt-2 flex flex-col gap-2">
            {rows.map((row, i) => (
              <li
                key={`${row.email}-${i}`}
                className="grid grid-cols-[1fr_auto] sm:grid-cols-[minmax(0,1fr)_120px_auto] gap-2 items-center"
              >
                <input
                  type="email"
                  value={row.email}
                  placeholder={t('emailPlaceholder')}
                  onChange={e => patchRow(i, { email: e.target.value })}
                  className="col-span-2 sm:col-span-1 min-w-0 rounded border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-blue-500"
                />
                <select
                  value={row.role}
                  onChange={e =>
                    patchRow(i, {
                      role: e.target.value as InviteRow['role'],
                    })
                  }
                  className="rounded border border-gray-300 px-2 py-1.5 text-sm"
                >
                  <option value="student">{t('roleStudent')}</option>
                  <option value="teacher">{t('roleTeacher')}</option>
                  <option value="admin">{t('roleAdmin')}</option>
                </select>
                <button
                  type="button"
                  onClick={() => removeRow(i)}
                  className="h-11 w-11 inline-flex items-center justify-center text-gray-500 hover:text-red-600"
                  aria-label={t('removeAriaLabel', { email: row.email })}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        </div>

        <button
          type="button"
          onClick={sendInvites}
          disabled={!payload.organization_id || rows.length === 0 || sending}
          className="rounded-lg bg-blue-600 px-4 py-2.5 text-white font-medium hover:bg-blue-700 disabled:bg-gray-300"
        >
          {sending ? t('sending') : t('sendInvites', { count: rows.length })}
        </button>

        {tierError && (
          <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            {tierError}{' '}
            <a
              href="/admin/billing"
              className="font-medium underline underline-offset-2"
            >
              {t('upgradePlan')}
            </a>
          </div>
        )}

        {results.length > 0 && (
          <ul className="text-xs text-gray-700 space-y-0.5">
            {results.map(r => (
              <li key={r.email} className="flex gap-2 items-start">
                <span className="shrink-0">{r.status === 'sent' ? '✓' : r.status === 'over_limit' ? '⏸' : '✗'}</span>
                <span className="font-mono min-w-0 break-all">{r.email}</span>
                {r.reason && <span className="text-gray-400 shrink-0">— {r.reason}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </SchoolOnboardingShell>
  );
}
