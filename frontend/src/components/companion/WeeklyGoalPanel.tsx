'use client';

/**
 * WeeklyGoalPanel — the companion weekly practice-days goal (spec line 365).
 * Replaces the daily-streak flame inside the companion surface (R2): shows
 * progress toward an adjustable weekly target that resets each week, with NO
 * guilt/penalty for a missed week. Mounts only inside the flag-gated companion
 * page; plain client fetch, no SWR (plan A6).
 *
 * The goal is purely motivational — it never gates or unlocks anything (R2).
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ANALYTICS_EVENTS, track } from '@/lib/analytics/events';

interface Goal {
  target: number;
  progress: number;
  met: boolean;
}

const TARGET_OPTIONS = [1, 2, 3, 4, 5, 6, 7];

export default function WeeklyGoalPanel() {
  const t = useTranslations('companion');
  const [goal, setGoal] = useState<Goal | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const res = await fetch('/api/gamification/companion/goal');
    if (!res.ok) return;
    const body = await res.json().catch(() => null);
    if (body) {
      setGoal({
        target: Number(body.target ?? 3),
        progress: Number(body.progress ?? 0),
        met: !!body.met,
      });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const changeTarget = async (target: number) => {
    if (busy) return;
    setBusy(true);
    try {
      const res = await fetch('/api/gamification/companion/goal', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target }),
      });
      if (res.ok) {
        track(ANALYTICS_EVENTS.COMPANION_WEEKLY_GOAL_UPDATED, { target, cohort: 'chess-empire' });
        await load();
      }
    } finally {
      setBusy(false);
    }
  };

  if (!goal) return null;

  const pct = goal.target > 0 ? Math.min(100, Math.round((goal.progress / goal.target) * 100)) : 0;

  return (
    <section className="mt-6 rounded-2xl border border-gray-200 p-4 dark:border-[#2a2a2a]">
      <header className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">{t('goal.title')}</h2>
        <label className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
          {t('goal.targetLabel')}
          <select
            value={goal.target}
            disabled={busy}
            onChange={(e) => changeTarget(Number(e.target.value))}
            className="rounded-lg border border-gray-200 bg-white px-2 py-1 text-sm text-gray-800 disabled:opacity-50 dark:border-[#2a2a2a] dark:bg-[#1f1f1f] dark:text-gray-200"
            aria-label={t('goal.targetLabel')}
          >
            {TARGET_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      </header>

      <div
        className="h-2 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-[#1f1f1f]"
        role="progressbar"
        aria-valuenow={goal.progress}
        aria-valuemin={0}
        aria-valuemax={goal.target}
      >
        <div
          className="h-full rounded-full bg-emerald-500 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>

      <p className="mt-2 text-sm font-medium text-gray-700 dark:text-gray-300">
        {t('goal.progress', { done: goal.progress, target: goal.target })}
      </p>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
        {goal.met ? t('goal.met') : t('goal.keepGoing')}
      </p>
    </section>
  );
}
