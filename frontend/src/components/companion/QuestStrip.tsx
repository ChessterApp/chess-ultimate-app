'use client';

/**
 * QuestStrip — the minimal companion quest strip (spec §7.2). Lists active
 * published quests with server-computed state + objective progress, lets the kid
 * start a quest (available → active), and celebrates the first-completion reward.
 * Completion is derived server-side from Watchtower evidence (never a client
 * flag). Mounts only inside the flag-gated companion page (hatched state); plain
 * client fetch, no SWR (plan A6). Quests never gate any educational path (R2).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { ANALYTICS_EVENTS, track } from '@/lib/analytics/events';
import { CelebrationOverlay } from '@/components/gamification/CelebrationOverlay';

type QuestState = 'locked' | 'available' | 'active' | 'objectives_complete' | 'completed';

interface Quest {
  id: string;
  version: number;
  title: { en: string; ru: string; kk: string };
  description: { en: string; ru: string; kk: string };
  state: QuestState;
  objectives: { done: number; total: number; complete: boolean };
  reward_granted: boolean;
  xp: number;
  coins: number;
}

function pick(copy: { en: string; ru: string; kk: string }, locale: string): string {
  if (locale === 'ru') return copy.ru;
  if (locale === 'kz') return copy.kk;
  return copy.en;
}

export default function QuestStrip() {
  const t = useTranslations('companion');
  const locale = useLocale();
  const [quests, setQuests] = useState<Quest[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [celebrate, setCelebrate] = useState<{ xp: number; coins: number } | null>(null);
  // Remember which quest completions we've already announced so a reconciled
  // reward (fired on read) only emits analytics once per mount.
  const announced = useRef<Set<string>>(new Set());

  const announce = useCallback((list: Quest[]) => {
    for (const q of list) {
      const key = `${q.id}:${q.version}`;
      if (q.state === 'completed' && q.reward_granted && !announced.current.has(key)) {
        announced.current.add(key);
        track(ANALYTICS_EVENTS.COMPANION_QUEST_COMPLETED, {
          quest_id: q.id,
          version: q.version,
          cohort: 'chess-empire',
        });
        track(ANALYTICS_EVENTS.COMPANION_REWARD_GRANTED, {
          source: 'quest',
          quest_id: q.id,
          xp: q.xp,
          coins: q.coins,
          cohort: 'chess-empire',
        });
        setCelebrate({ xp: q.xp, coins: q.coins });
      }
    }
  }, []);

  const load = useCallback(async () => {
    const res = await fetch('/api/gamification/companion/quests');
    if (!res.ok) return;
    const body = await res.json().catch(() => null);
    const list = Array.isArray(body?.quests) ? (body.quests as Quest[]) : [];
    setQuests(list);
    announce(list);
  }, [announce]);

  useEffect(() => {
    load();
  }, [load]);

  const start = async (quest: Quest) => {
    if (busy) return;
    setBusy(quest.id);
    try {
      const res = await fetch(
        `/api/gamification/companion/quests/${encodeURIComponent(quest.id)}/start`,
        { method: 'POST' },
      );
      if (!res.ok) return;
      track(ANALYTICS_EVENTS.COMPANION_QUEST_STARTED, {
        quest_id: quest.id,
        version: quest.version,
        cohort: 'chess-empire',
      });
      const body = await res.json().catch(() => null);
      if (body) announce([body as Quest]);
      await load();
    } finally {
      setBusy(null);
    }
  };

  if (!quests || quests.length === 0) return null;

  return (
    <section className="mt-6 rounded-2xl border border-gray-200 p-4 dark:border-[#2a2a2a]">
      <header className="mb-3 text-center">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">{t('quest.title')}</h2>
      </header>

      <ul className="space-y-2">
        {quests.map((q) => {
          const done = q.state === 'completed';
          return (
            <li
              key={`${q.id}:${q.version}`}
              className="flex items-center justify-between gap-3 rounded-xl bg-gray-50 px-3 py-2 dark:bg-[#1f1f1f]"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-gray-800 dark:text-gray-200">
                  <span aria-hidden className="mr-1">
                    {done ? '🏆' : '🗺️'}
                  </span>
                  {pick(q.title, locale)}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {t('quest.progress', { done: q.objectives.done, total: q.objectives.total })}
                </p>
              </div>
              {done ? (
                <span className="shrink-0 text-xs font-semibold text-emerald-600">
                  {t('quest.completed')}
                </span>
              ) : q.state === 'active' || q.state === 'objectives_complete' ? (
                <span className="shrink-0 text-xs font-medium text-indigo-500">
                  {t('quest.active')}
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => start(q)}
                  disabled={busy === q.id}
                  className="shrink-0 rounded-full bg-indigo-600 px-3 py-1 text-xs font-semibold text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
                >
                  {t('quest.start')}
                </button>
              )}
            </li>
          );
        })}
      </ul>

      {celebrate && (
        <CelebrationOverlay
          type="courseComplete"
          title={t('quest.completed')}
          subtitle={t('quest.reward', { xp: celebrate.xp, coins: celebrate.coins })}
          xpGained={celebrate.xp}
          onClose={() => setCelebrate(null)}
        />
      )}
    </section>
  );
}
