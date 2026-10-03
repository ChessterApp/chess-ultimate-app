'use client';

/**
 * WatchtowerPanel — the companion Watchtower chapter surface (spec §7.3). Lists
 * the six learning nodes with server-computed completion, opens one at a time on
 * a board, submits to /api/gamification/companion/watchtower (server-judged), and
 * celebrates the chapter-completion reward. Mounts only inside the flag-gated
 * companion page (hatched state); plain client fetch, no SWR (plan A6).
 */
import { useCallback, useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import type { Submission } from '@/lib/companion/assessment';
import { CelebrationOverlay } from '@/components/gamification/CelebrationOverlay';
import WatchtowerBoard from './WatchtowerBoard';

interface Node {
  node: string;
  fen: string;
  validator: string;
  prompt: { en: string; ru: string; kk: string };
  completed: boolean;
}
interface View {
  nodes: Node[];
  completed_count: number;
  total: number;
  chapter_complete: boolean;
}

function pickPrompt(p: Node['prompt'], locale: string): string {
  if (locale === 'ru') return p.ru;
  if (locale === 'kz') return p.kk;
  return p.en;
}

export default function WatchtowerPanel() {
  const t = useTranslations('companion');
  const locale = useLocale();
  const [view, setView] = useState<View | null>(null);
  const [active, setActive] = useState<Node | null>(null);
  const [feedback, setFeedback] = useState<'correct' | 'incorrect' | null>(null);
  const [busy, setBusy] = useState(false);
  const [celebrate, setCelebrate] = useState<{ xp: number; coins: number } | null>(null);

  const load = useCallback(async () => {
    const res = await fetch('/api/gamification/companion/watchtower');
    if (!res.ok) return;
    const body = await res.json().catch(() => null);
    const nodes = Array.isArray(body?.nodes) ? (body.nodes as Node[]) : [];
    setView({
      nodes,
      completed_count: Number(body?.completed_count ?? 0),
      total: Number(body?.total ?? nodes.length),
      chapter_complete: !!body?.chapter_complete,
    });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async (submission: Submission) => {
    if (!active || busy) return;
    setBusy(true);
    try {
      const res = await fetch('/api/gamification/companion/watchtower', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node: active.node, submission }),
      });
      const body = await res.json().catch(() => ({}));
      if (res.ok && body?.correct) {
        setFeedback('correct');
        if (body?.chapter_complete && body?.reward_granted) {
          setCelebrate({ xp: Number(body.xp ?? 0), coins: Number(body.coins ?? 0) });
        }
        await load();
        setActive(null);
      } else {
        setFeedback('incorrect');
      }
    } finally {
      setBusy(false);
    }
  };

  if (!view || view.nodes.length === 0) return null;

  return (
    <section className="mt-8 rounded-2xl border border-gray-200 p-4 dark:border-[#2a2a2a]">
      <header className="mb-3 text-center">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          {t('watchtower.title')}
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {t('watchtower.progress', { done: view.completed_count, total: view.total })}
        </p>
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
            submitLabel={t('watchtower.submit')}
            clearLabel={t('watchtower.clear')}
          />
          {feedback && (
            <p
              className={`mt-3 text-center text-sm font-medium ${
                feedback === 'correct' ? 'text-green-600' : 'text-amber-600'
              }`}
            >
              {feedback === 'correct' ? t('watchtower.correct') : t('watchtower.incorrect')}
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
              {t('watchtower.back')}
            </button>
          </div>
        </div>
      ) : (
        <ul className="space-y-2">
          {view.nodes.map((n) => (
            <li
              key={n.node}
              className="flex items-center justify-between rounded-xl bg-gray-50 px-3 py-2 dark:bg-[#1f1f1f]"
            >
              <span className="flex items-center gap-2 text-sm text-gray-800 dark:text-gray-200">
                <span aria-hidden>{n.completed ? '✅' : '•'}</span>
                {pickPrompt(n.prompt, locale)}
              </span>
              <button
                type="button"
                onClick={() => {
                  setActive(n);
                  setFeedback(null);
                }}
                className="shrink-0 rounded-full bg-green-600 px-3 py-1 text-xs font-semibold text-white transition-colors hover:bg-green-700"
              >
                {n.completed ? t('watchtower.replay') : t('watchtower.play')}
              </button>
            </li>
          ))}
        </ul>
      )}

      {celebrate && (
        <CelebrationOverlay
          type="courseComplete"
          title={t('watchtower.chapterComplete')}
          subtitle={t('watchtower.chapterReward', { xp: celebrate.xp, coins: celebrate.coins })}
          xpGained={celebrate.xp}
          onClose={() => setCelebrate(null)}
        />
      )}
    </section>
  );
}
