'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { COMPANION_NAME_MAX } from '@/lib/companion/state';
import { ANALYTICS_EVENTS, track } from '@/lib/analytics/events';
import CompanionAnimation from './CompanionAnimation';

/** What the parent's hatch POST resolves to (drives the reveal + reward display). */
export interface HatchOutcome {
  ok: boolean;
  /** The server-sanitized, committed companion name. */
  name?: string;
  reward_granted?: boolean;
  xp?: number;
  coins?: number;
  starter_granted?: boolean;
  /** When !ok: 'not_ready' | 'invalid_name' | 'error' — for a friendly message. */
  error?: string;
}

interface FoxRevealProps {
  /** 'hatch' runs naming → commit → reveal; 'replay' just re-plays the scene. */
  mode: 'hatch' | 'replay';
  /** Committed companion name (replay mode) / default prefill (hatch mode). */
  initialName?: string | null;
  /** Commit the hatch (POST). Only called in 'hatch' mode. */
  onHatch?: (name: string) => Promise<HatchOutcome>;
  /** Close/dismiss the reveal (reward is already committed — never cancels it). */
  onClose: () => void;
}

type Phase = 'naming' | 'hatching' | 'revealed';

/**
 * The hatch moment (spec §3.4 / §10.2): name the companion, commit the hatch
 * (rewards + identity persist BEFORE playback), then play the ~8s fox hatch scene
 * — skippable from the start and replayable later from the journal. Skipping,
 * closing, or replaying never cancels the hatch or creates a second companion
 * (idempotency lives in the RPC). Only mounted when the feature flag is on (the
 * /companion page 404s otherwise), so this never renders while dark.
 */
export default function FoxReveal({ mode, initialName, onHatch, onClose }: FoxRevealProps) {
  const t = useTranslations('companion');
  const [phase, setPhase] = useState<Phase>(mode === 'replay' ? 'hatching' : 'naming');
  const [name, setName] = useState(initialName ?? '');
  const [committedName, setCommittedName] = useState(initialName ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<HatchOutcome | null>(null);

  const confirmHatch = async () => {
    const trimmed = name.trim();
    if (!trimmed || !onHatch) {
      setError(t('hatch.nameRequired'));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await onHatch(trimmed);
      if (!res.ok) {
        setError(res.error === 'not_ready' ? t('hatch.notReady') : t('hatch.failed'));
        return;
      }
      // Analytics (spec §13) — no PII: the name itself is never sent, only that
      // a companion was named + hatched, with the reward outcome.
      track(ANALYTICS_EVENTS.COMPANION_NAMED, { named: true, cohort: 'chess-empire' });
      track(ANALYTICS_EVENTS.COMPANION_HATCHED, { cohort: 'chess-empire' });
      if (res.reward_granted) {
        track(ANALYTICS_EVENTS.COMPANION_REWARD_GRANTED, {
          source: 'hatch',
          xp: res.xp ?? 0,
          coins: res.coins ?? 0,
          cohort: 'chess-empire',
        });
      }
      setOutcome(res);
      setCommittedName(res.name || trimmed);
      setPhase('hatching');
    } catch {
      setError(t('hatch.failed'));
    } finally {
      setBusy(false);
    }
  };

  const foxLabel = t('hatch.foxAlt', { name: committedName || t('eggs.fox') });

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t('hatch.title', { name: committedName || t('eggs.fox') })}
      className="fixed inset-0 z-50 flex items-center justify-center"
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      <div className="relative mx-4 w-full max-w-sm rounded-3xl bg-white p-6 text-center shadow-2xl dark:bg-[#161616]">
        {phase === 'naming' && (
          <>
            <h2 className="mb-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
              {t('hatch.nameLabel')}
            </h2>
            <p className="mb-5 text-sm text-gray-500 dark:text-gray-400">{t('hatch.subtitle')}</p>
            <CompanionAnimation state="idle" label={t('eggs.fox')} size={160} />
            <input
              type="text"
              value={name}
              maxLength={COMPANION_NAME_MAX}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('hatch.namePlaceholder')}
              aria-label={t('hatch.nameLabel')}
              className="mt-5 w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-center text-lg text-gray-900 focus:border-purple-400 focus:outline-none dark:border-[#2a2a2a] dark:bg-[#1a1a1a] dark:text-gray-100"
            />
            {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
            <button
              type="button"
              disabled={busy || name.trim().length === 0}
              onClick={confirmHatch}
              className="mt-5 w-full rounded-xl bg-purple-600 px-6 py-3 font-semibold text-white transition-colors hover:bg-purple-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? t('hatch.hatching') : t('hatch.confirm')}
            </button>
          </>
        )}

        {phase === 'hatching' && (
          <>
            <CompanionAnimation
              state="hatch"
              label={foxLabel}
              size={220}
              loop={false}
              onComplete={() => setPhase('revealed')}
            />
            <button
              type="button"
              onClick={() => setPhase('revealed')}
              className="mt-5 w-full rounded-xl border border-gray-200 px-6 py-3 font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-[#2a2a2a] dark:text-gray-200 dark:hover:bg-[#1f1f1f]"
            >
              {t('hatch.skip')}
            </button>
          </>
        )}

        {phase === 'revealed' && (
          <>
            <h2 className="mb-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
              {t('hatch.title', { name: committedName || t('eggs.fox') })}
            </h2>
            <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">{t('hatch.subtitle')}</p>
            <CompanionAnimation state="greet" label={foxLabel} size={200} />
            {mode === 'hatch' && outcome?.reward_granted && (
              <p className="mt-4 inline-block rounded-full bg-amber-100 px-4 py-2 text-sm font-semibold text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
                {t('hatch.reward', { xp: outcome.xp ?? 0, coins: outcome.coins ?? 0 })}
              </p>
            )}
            {mode === 'hatch' && outcome?.starter_granted && (
              <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">{t('hatch.starter')}</p>
            )}
            <button
              type="button"
              onClick={onClose}
              className="mt-6 w-full rounded-xl bg-purple-600 px-6 py-3 font-semibold text-white transition-colors hover:bg-purple-700"
            >
              {t('hatch.continue')}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
