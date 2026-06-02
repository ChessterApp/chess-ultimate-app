'use client';

import { useState } from 'react';

import { BrandPreviewPanel } from '@/components/school-onboarding/BrandPreviewPanel';
import { SchoolOnboardingShell } from '@/components/school-onboarding/SchoolOnboardingShell';
import { useWizard } from '@/components/school-onboarding/WizardState';

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
  const [bulkText, setBulkText] = useState('');
  const [rows, setRows] = useState<InviteRow[]>(payload.invites as InviteRow[] || []);
  const [sending, setSending] = useState(false);
  const [results, setResults] = useState<SendResult[]>([]);
  const [tierError, setTierError] = useState<string | null>(null);

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
        out.push({ email: row.email, status: 'failed', reason: 'Invalid email' });
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
            `Seat limit reached on your ${body.plan} plan (${body.current_count}/${body.seat_cap}). Upgrade to send the rest.`,
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
        out.push({ email: row.email, status: 'failed', reason: 'Network error' });
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
      title="Invite your students."
      subtitle="Add a few now — you can bulk-import more later from /admin/students."
      backTo="/for-schools/start/brand"
      preview={<BrandPreviewPanel payload={payload} />}
      nextLabel="Finish →"
      canAdvance={results.some(r => r.status === 'sent')}
    >
      <div className="flex flex-col gap-4">
        <div>
          <label className="text-sm font-medium text-gray-700">
            Paste a list of emails
          </label>
          <textarea
            value={bulkText}
            onChange={e => setBulkText(e.target.value)}
            placeholder={'student1@example.com\nstudent2@example.com'}
            rows={3}
            className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-100 outline-none"
          />
          <button
            type="button"
            onClick={appendFromBulk}
            className="mt-2 text-xs rounded border border-gray-300 px-2.5 py-1 hover:bg-gray-50"
          >
            Add to list
          </button>
        </div>

        <div>
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-gray-700">
              Invitees ({rows.length})
            </label>
            <button
              type="button"
              onClick={appendOne}
              className="text-xs text-blue-600 hover:underline"
            >
              + Add another
            </button>
          </div>
          <ul className="mt-2 flex flex-col gap-2">
            {rows.map((row, i) => (
              <li
                key={`${row.email}-${i}`}
                className="grid grid-cols-[1fr_120px_auto] gap-2 items-center"
              >
                <input
                  type="email"
                  value={row.email}
                  placeholder="student@example.com"
                  onChange={e => patchRow(i, { email: e.target.value })}
                  className="rounded border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-blue-500"
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
                  <option value="student">Student</option>
                  <option value="teacher">Teacher</option>
                  <option value="admin">Admin</option>
                </select>
                <button
                  type="button"
                  onClick={() => removeRow(i)}
                  className="text-xs text-gray-500 hover:text-red-600"
                  aria-label={`Remove ${row.email}`}
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
          {sending ? 'Sending…' : `Send ${rows.length} invites`}
        </button>

        {tierError && (
          <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            {tierError}{' '}
            <a
              href="/admin/billing"
              className="font-medium underline underline-offset-2"
            >
              Upgrade plan →
            </a>
          </div>
        )}

        {results.length > 0 && (
          <ul className="text-xs text-gray-700 space-y-0.5">
            {results.map(r => (
              <li key={r.email} className="flex gap-2">
                <span>{r.status === 'sent' ? '✓' : r.status === 'over_limit' ? '⏸' : '✗'}</span>
                <span className="font-mono">{r.email}</span>
                {r.reason && <span className="text-gray-400">— {r.reason}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </SchoolOnboardingShell>
  );
}
