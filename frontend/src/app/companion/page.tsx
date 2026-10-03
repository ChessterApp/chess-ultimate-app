'use client';

import { useCallback, useEffect, useState } from 'react';
import { notFound } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { COMPANION_ENABLED } from '@/lib/feature-flags';
import LoadingScreen from '@/components/LoadingScreen';
import EggAnimation from '@/components/companion/EggAnimation';
import EggChooser from '@/components/companion/EggChooser';
import CompetencyRing, { type RingCompetency } from '@/components/companion/CompetencyRing';
import CompanionAnimation from '@/components/companion/CompanionAnimation';
import FoxReveal, { type HatchOutcome } from '@/components/companion/FoxReveal';
import WatchtowerPanel from '@/components/companion/WatchtowerPanel';
import DueReviewPanel from '@/components/companion/DueReviewPanel';

interface CompanionView {
  companion: { species: string | null; name: string | null; stage: string; hatched_at: string | null } | null;
  competencies: RingCompetency[];
  hatch_ready: boolean;
  hatch_progress: number;
}

export default function CompanionPage() {
  // UI kill-switch: the whole surface 404s while the feature is dark.
  if (!COMPANION_ENABLED) notFound();
  return <CompanionInner />;
}

function CompanionInner() {
  const t = useTranslations('companion');
  const [data, setData] = useState<CompanionView | null>(null);
  const [loading, setLoading] = useState(true);
  const [linked, setLinked] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [gone, setGone] = useState(false);
  const [reveal, setReveal] = useState<'hatch' | 'replay' | null>(null);

  const load = useCallback(async () => {
    const res = await fetch('/api/gamification/companion');
    if (res.status === 404) {
      // Server flag off — flag it and let render call notFound() (throwing from
      // an async callback would not hit the not-found boundary).
      setGone(true);
      setLoading(false);
      return;
    }
    if (res.status === 403) {
      setLinked(false);
      setLoading(false);
      return;
    }
    if (res.ok) setData(await res.json());
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const chooseEgg = async (species: string) => {
    setBusy(species);
    try {
      const res = await fetch('/api/gamification/companion/egg', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ species }),
      });
      if (res.ok) await load();
    } finally {
      setBusy(null);
    }
  };

  // Commit the hatch (rewards + identity persist server-side BEFORE the reveal
  // plays). Idempotent server-side; reloads the view on success.
  const hatch = useCallback(async (name: string): Promise<HatchOutcome> => {
    const res = await fetch('/api/gamification/companion/hatch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      return { ok: false, error: res.status === 409 ? 'not_ready' : 'error' };
    }
    await load();
    return {
      ok: true,
      name: body?.companion?.name ?? name,
      reward_granted: !!body?.reward_granted,
      xp: Number(body?.xp ?? 0),
      coins: Number(body?.coins ?? 0),
      starter_granted: !!body?.starter_granted,
    };
  }, [load]);

  if (gone) notFound();
  if (loading) return <LoadingScreen isVisible={true} />;

  if (!linked) {
    return (
      <div className="mx-auto max-w-md p-8 text-center">
        <h1 className="mb-2 text-xl font-bold text-gray-900 dark:text-gray-100">
          {t('notLinkedTitle')}
        </h1>
        <p className="text-gray-500 dark:text-gray-400">{t('notLinkedBody')}</p>
      </div>
    );
  }

  const chosen = data?.companion?.species ?? null;
  if (!chosen) {
    return <EggChooser onChoose={chooseEgg} busy={busy} />;
  }

  const hatched = data?.companion?.stage === 'hatched';
  const name = data?.companion?.name ?? null;

  return (
    <div className="mx-auto max-w-lg px-4 py-6">
      <header className="mb-4 text-center">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{t('title')}</h1>
        <p className="text-gray-500 dark:text-gray-400">{t('subtitle')}</p>
      </header>

      {hatched ? (
        <div className="text-center">
          <CompanionAnimation
            state="idle"
            label={t('hatch.foxAlt', { name: name || t('eggs.fox') })}
          />
          {name && (
            <p className="mt-2 text-lg font-semibold text-gray-900 dark:text-gray-100">{name}</p>
          )}
          <button
            type="button"
            onClick={() => setReveal('replay')}
            className="mt-3 rounded-full border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 dark:border-[#2a2a2a] dark:text-gray-300 dark:hover:bg-[#1f1f1f]"
          >
            {t('hatch.replay')}
          </button>
        </div>
      ) : (
        <>
          <EggAnimation species={chosen} label={t('eggAlt', { name: t(`eggs.${chosen}`) })} />
          {data!.hatch_ready && (
            <div className="mt-4 text-center">
              <button
                type="button"
                onClick={() => setReveal('hatch')}
                className="rounded-xl bg-green-600 px-6 py-3 font-semibold text-white transition-colors hover:bg-green-700"
              >
                {t('hatch.cta')}
              </button>
            </div>
          )}
        </>
      )}

      <CompetencyRing
        competencies={data!.competencies}
        hatchProgress={data!.hatch_progress}
        hatchReady={data!.hatch_ready}
      />

      {/* Post-hatch: the Watchtower chapter + pull-based review surface (Phase 4). */}
      {hatched && (
        <>
          <WatchtowerPanel />
          <DueReviewPanel />
        </>
      )}

      {reveal && (
        <FoxReveal
          mode={reveal}
          initialName={name}
          onHatch={hatch}
          onClose={() => setReveal(null)}
        />
      )}
    </div>
  );
}
