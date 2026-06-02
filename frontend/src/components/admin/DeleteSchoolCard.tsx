'use client';

// PRD §7 — self-serve delete-school request card.
//
// Render states:
//   - Idle: red danger card with description + "Delete this school" button.
//   - Modal open: school name + type-confirm input + final delete button
//     (disabled until input matches the school name exactly).
//   - Scheduled: replaces the card with the date and a "email support" hint.
//     Triggered either when the org already has `deletionRequestedAt` on
//     load, or immediately after a successful POST.

import { useState } from 'react';

interface DeleteSchoolCardProps {
  orgId: string;
  orgName: string;
  initialDeletionRequestedAt: string | null;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
}

export default function DeleteSchoolCard({
  orgId,
  orgName,
  initialDeletionRequestedAt,
}: DeleteSchoolCardProps) {
  const [scheduledAt, setScheduledAt] = useState<string | null>(
    initialDeletionRequestedAt,
  );
  const [modalOpen, setModalOpen] = useState(false);
  const [typed, setTyped] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (scheduledAt) {
    return (
      <section
        data-testid="delete-school-scheduled"
        className="rounded-xl border border-red-200 dark:border-red-900/50 bg-red-50/40 dark:bg-red-950/20 p-6"
      >
        <h2 className="text-lg font-semibold text-red-900 dark:text-red-200 mb-2">
          Deletion scheduled
        </h2>
        <p className="text-sm text-red-900/80 dark:text-red-200/80">
          Your school is scheduled for deletion on{' '}
          <strong>{formatDate(scheduledAt)}</strong>. Email{' '}
          <a
            href="mailto:support@chesster.io"
            className="underline font-medium"
          >
            support@chesster.io
          </a>{' '}
          within this window to cancel.
        </p>
      </section>
    );
  }

  const confirmExactMatch = typed === orgName;

  async function handleSubmit() {
    if (!confirmExactMatch || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/admin/organizations/${orgId}/delete-request`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ confirm_name: typed }),
        },
      );
      const data = (await res.json().catch(() => ({}))) as {
        deletion_requested_at?: string;
        error?: string;
      };
      if (!res.ok || !data.deletion_requested_at) {
        setError(data.error || 'Failed to schedule deletion. Try again.');
        return;
      }
      setScheduledAt(data.deletion_requested_at);
      setModalOpen(false);
    } catch {
      setError('Network error. Try again.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <section
        data-testid="delete-school-card"
        className="rounded-xl border border-red-200 dark:border-red-900/50 bg-white dark:bg-gray-800 p-6"
      >
        <h2 className="text-lg font-semibold text-red-700 dark:text-red-400 mb-2">
          Delete school
        </h2>
        <p className="text-sm text-gray-700 dark:text-gray-300 mb-4">
          Schedules deletion in 30 days. All students, content, and billing
          will be removed. You can email support to cancel within that window.
        </p>
        <button
          type="button"
          onClick={() => {
            setTyped('');
            setError(null);
            setModalOpen(true);
          }}
          className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors"
        >
          Delete this school
        </button>
      </section>

      {modalOpen && (
        <div
          data-testid="delete-school-modal"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-school-modal-title"
        >
          <div className="w-full max-w-md rounded-xl bg-white dark:bg-gray-900 p-6 shadow-xl">
            <h3
              id="delete-school-modal-title"
              className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2"
            >
              Delete {orgName}?
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              This schedules deletion in 30 days. To confirm, type{' '}
              <strong className="text-gray-900 dark:text-gray-100">
                {orgName}
              </strong>{' '}
              below.
            </p>
            <label
              htmlFor="delete-school-confirm-input"
              className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Type &quot;{orgName}&quot; to confirm
            </label>
            <input
              id="delete-school-confirm-input"
              type="text"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoFocus
              autoComplete="off"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm mb-4"
            />
            {error && (
              <p
                data-testid="delete-school-error"
                className="text-sm text-red-600 dark:text-red-400 mb-3"
              >
                {error}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                disabled={submitting}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!confirmExactMatch || submitting}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submitting ? 'Scheduling…' : 'Delete school'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
