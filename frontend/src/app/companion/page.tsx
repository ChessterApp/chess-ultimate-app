'use client';

import { useCallback, useEffect, useState } from 'react';
import { notFound } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { COMPANION_ENABLED } from '@/lib/feature-flags';
import LoadingScreen from '@/components/LoadingScreen';
import EggAnimation from '@/components/companion/EggAnimation';
import EggChooser from '@/components/companion/EggChooser';
import CompetencyRing, { type RingCompetency } from '@/components/companion/CompetencyRing';

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

  return (
    <div className="mx-auto max-w-lg px-4 py-6">
      <header className="mb-4 text-center">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{t('title')}</h1>
        <p className="text-gray-500 dark:text-gray-400">{t('subtitle')}</p>
      </header>
      <EggAnimation species={chosen} label={t('eggAlt', { name: t(`eggs.${chosen}`) })} />
      <CompetencyRing
        competencies={data!.competencies}
        hatchProgress={data!.hatch_progress}
        hatchReady={data!.hatch_ready}
      />
    </div>
  );
}
