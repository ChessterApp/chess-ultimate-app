'use client';

/**
 * DueReviewPanel — the companion pull-based review surface (plan A4, spec §6.3).
 * Fetches the due queue, starts a review (issues a review-mode assignment), plays
 * one task on a board, and submits to /api/gamification/companion/reviews (server
 * judges + advances the 1/3/7/14 ladder + grants the due_review reward). Mounts
 * only inside the flag-gated companion page (hatched state); plain client fetch.
 */
import { useCallback, useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import type { Submission } from '@/lib/companion/assessment';
import WatchtowerBoard from './WatchtowerBoard';

interface DueItem {
  competency: string;
  title_en: string;
  title_ru: string;
  title_kk: string;
  rung: number;
}
interface ActiveTask {
  assignment_id: string;
  fen: string;
  validator: string;
  prompt: { en: string; ru: string; kk: string };
}

function pickTitle(it: DueItem, locale: string): string {
  if (locale === 'ru') return it.title_ru;
  if (locale === 'kz') return it.title_kk;
  return it.title_en;
}
function pickPrompt(p: ActiveTask['prompt'], locale: string): string {
  if (locale === 'ru') return p.ru;
  if (locale === 'kz') return p.kk;
  return p.en;
}

export default function DueReviewPanel() {
  const t = useTranslations('companion');
  const locale = useLocale();
  const [due, setDue] = useState<DueItem[] | null>(null);
  const [active, setActive] = useState<ActiveTask | null>(null);
  const [feedback, setFeedback] = useState<'correct' | 'incorrect' | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const res = await fetch('/api/gamification/companion/reviews/due');
    if (!res.ok) return;
    const body = await res.json().catch(() => null);
    setDue(Array.isArray(body?.due) ? (body.due as DueItem[]) : []);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const start = async (competency: string) => {
    if (busy) return;
    setBusy(true);
    setFeedback(null);
    try {
      const res = await fetch('/api/gamification/companion/assignments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ competency, mode: 'review' }),
      });
      if (!res.ok) return;
      const task = await res.json().catch(() => null);
      if (task?.assignment_id) setActive(task as ActiveTask);
    } finally {
      setBusy(false);
    }
  };

  const submit = async (submission: Submission) => {
    if (!active || busy) return;
    setBusy(true);
    try {
      const res = await fetch('/api/gamification/companion/reviews', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ assignment_id: active.assignment_id, submission }),
      });
      const body = await res.json().catch(() => ({}));
      if (res.ok && body?.correct) {
        setFeedback('correct');
        await load();
        setActive(null);
      } else {
        setFeedback('incorrect');
      }
    } finally {
      setBusy(false);
    }
  };

  if (!due) return null;

  return (
    <section className="mt-6 rounded-2xl border border-gray-200 p-4 dark:border-[#2a2a2a]">
      <header className="mb-3 text-center">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">{t('review.title')}</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">{t('review.subtitle')}</p>
      </header>

      {active ? (
        <div>
          <p className="mb-3 text-center text-gray-800 dark:text-gray-200">
            {pickPrompt(active.prompt, locale)}
          </p>
          <WatchtowerBoard
            fen={active.fen}
            validator={active.validator}
            onSubmit={submit}
            disabled={busy}
            submitLabel={t('review.submit')}
            clearLabel={t('review.clear')}
          />
          {feedback && (
            <p
              className={`mt-3 text-center text-sm font-medium ${
                feedback === 'correct' ? 'text-green-600' : 'text-amber-600'
              }`}
            >
              {feedback === 'correct' ? t('review.correct') : t('review.incorrect')}
            </p>
          )}
          <div className="mt-3 text-center">
            <button
              type="button"
              onClick={() => {
                setActive(null);
                setFeedback(null);
              }}
              className="text-sm font-medium text-gray-500 underline-offset-2 hover:underline dark:text-gray-400"
            >
              {t('review.back')}
            </button>
          </div>
        </div>
      ) : due.length === 0 ? (
        <p className="text-center text-sm text-gray-500 dark:text-gray-400">
          {t('review.allCaught')}
        </p>
      ) : (
        <ul className="space-y-2">
          {due.slice(0, 3).map((it) => (
            <li
              key={it.competency}
              className="flex items-center justify-between rounded-xl bg-gray-50 px-3 py-2 dark:bg-[#1f1f1f]"
            >
              <span className="text-sm text-gray-800 dark:text-gray-200">
                {pickTitle(it, locale)}
                {it.rung > 0 && (
                  <span className="ml-2 text-xs text-gray-400">
                    {t('review.rung', { rung: it.rung })}
                  </span>
                )}
              </span>
              <button
                type="button"
                onClick={() => start(it.competency)}
                disabled={busy}
                className="shrink-0 rounded-full bg-indigo-600 px-3 py-1 text-xs font-semibold text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
              >
                {t('review.start')}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
