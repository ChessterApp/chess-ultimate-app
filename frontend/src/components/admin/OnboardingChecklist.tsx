'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import {
  computeChecklist,
  completionPercentage,
  isAllCompleted,
  shouldShowChecklist,
  type ChecklistSnapshot,
} from '@/lib/onboarding-checklist';
import { ANALYTICS_EVENTS, track } from '@/lib/analytics/events';

// PRD §11.2 #5 — In-dashboard 24h onboarding checklist.

interface Props {
  snapshot: ChecklistSnapshot;
}

export function OnboardingChecklist({ snapshot }: Props) {
  const t = useTranslations('schoolOnboarding.admin.dashboard');
  const items = computeChecklist(snapshot);
  const visibleItems = items.filter(i => !i.hidden);
  const percent = completionPercentage(items);
  const allDone = isAllCompleted(items);
  const [shotConfetti, setShotConfetti] = useState(false);

  useEffect(() => {
    track(ANALYTICS_EVENTS.ONBOARDING_CHECKLIST_VIEWED, { percent });
    if (allDone && !shotConfetti) {
      track(ANALYTICS_EVENTS.ONBOARDING_CHECKLIST_COMPLETED);
      setShotConfetti(true);
    }
  }, [percent, allDone, shotConfetti]);

  if (!shouldShowChecklist(snapshot)) return null;

  return (
    <section
      data-testid="onboarding-checklist"
      className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6 mb-6"
    >
      <header className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          {allDone ? t('checklistAllDone') : t('checklistGetRunning')}
        </h2>
        <span className="text-sm text-gray-500">{t('checklistPercent', { percent })}</span>
      </header>

      <div className="h-2 rounded-full bg-gray-100 dark:bg-gray-700 mb-4 overflow-hidden">
        <div
          className="h-full transition-all"
          style={{ width: `${percent}%`, backgroundColor: 'var(--brand-primary)' }}
        />
      </div>

      <ul className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
        {visibleItems.map(item => {
          const label = t(`checklistItems.${item.id}`);
          return (
            <li
              key={item.id}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 border ${
                item.completed
                  ? 'border-green-200 bg-green-50 dark:bg-green-900/10'
                  : 'border-gray-200 dark:border-gray-700'
              }`}
            >
              <span
                aria-hidden
                className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-xs ${
                  item.completed
                    ? 'bg-green-600 text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-400'
                }`}
              >
                {item.completed ? '✓' : '○'}
              </span>
              {item.completed ? (
                <span className="text-gray-700 dark:text-gray-300 line-through">{label}</span>
              ) : (
                <Link
                  href={item.href}
                  onClick={() =>
                    track(ANALYTICS_EVENTS.ONBOARDING_CHECKLIST_ITEM_COMPLETED, { item: item.id })
                  }
                  className="text-blue-600 hover:underline"
                >
                  {label}
                </Link>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
