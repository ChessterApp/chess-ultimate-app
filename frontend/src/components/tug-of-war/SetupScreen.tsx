/**
 * SetupScreen — team names, difficulty band and theme picker, then Start.
 * Selections drive the live puzzle prefetch (see lib/tug-of-war/prefetch.ts).
 */

'use client';

import { useState } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import { TUG_LEVELS, TUG_THEMES, type TugLevel } from '@/lib/tug-of-war/prefetch';

export interface StartConfig {
  teamA: string;
  teamB: string;
  level: TugLevel;
  themes: string[];
}

interface SetupScreenProps {
  initialTeamA: string;
  initialTeamB: string;
  onStart: (config: StartConfig) => void;
  loading?: boolean;
}

export default function SetupScreen({
  initialTeamA,
  initialTeamB,
  onStart,
  loading = false,
}: SetupScreenProps) {
  const t = useTranslations('tugOfWar');
  const locale = useLocale();
  const [teamA, setTeamA] = useState(initialTeamA);
  const [teamB, setTeamB] = useState(initialTeamB);
  const [level, setLevel] = useState<TugLevel>('knight');
  const [themes, setThemes] = useState<string[]>([]);

  const toggleTheme = (tag: string) =>
    setThemes((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    );

  const howLines = t.raw('how') as string[];

  return (
    <div className="relative mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center gap-8 px-6 py-10 text-white">
      <LanguageSwitcher
        currentLocale={locale}
        variant="minimal"
        className="absolute right-4 top-4 z-50 [&_button]:text-white/80 [&_button]:hover:bg-white/10 [&_button]:hover:text-white"
      />
      <div className="text-center">
        <h1 className="text-4xl font-black tracking-tight sm:text-5xl">{t('title')}</h1>
        <p className="mt-2 text-lg text-white/70">{t('subtitle')}</p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (loading) return;
          onStart({ teamA, teamB, level, themes });
        }}
        className="w-full rounded-2xl border border-white/10 bg-white/5 p-6 sm:p-8"
      >
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <label className="flex flex-col gap-2">
            <span className="text-sm font-semibold text-blue-300">{t('teamALabel')}</span>
            <input
              value={teamA}
              onChange={(e) => setTeamA(e.target.value)}
              maxLength={24}
              className="rounded-lg border border-blue-500/40 bg-slate-900/70 px-4 py-3 text-lg font-semibold outline-none focus:border-blue-400"
            />
          </label>
          <label className="flex flex-col gap-2">
            <span className="text-sm font-semibold text-orange-300">{t('teamBLabel')}</span>
            <input
              value={teamB}
              onChange={(e) => setTeamB(e.target.value)}
              maxLength={24}
              className="rounded-lg border border-orange-500/40 bg-slate-900/70 px-4 py-3 text-lg font-semibold outline-none focus:border-orange-400"
            />
          </label>
        </div>

        <fieldset className="mt-6">
          <legend className="mb-2 text-sm font-semibold text-white/70">{t('levelLabel')}</legend>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {TUG_LEVELS.map((l) => (
              <button
                key={l.id}
                type="button"
                aria-pressed={level === l.id}
                onClick={() => setLevel(l.id)}
                className={`rounded-lg border px-3 py-2 text-sm font-semibold transition ${
                  level === l.id
                    ? 'border-white bg-white text-slate-900'
                    : 'border-white/20 bg-slate-900/50 text-white/80 hover:border-white/50'
                }`}
              >
                {t(`levels.${l.id}`)}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className="mt-5">
          <legend className="mb-2 text-sm font-semibold text-white/70">{t('themesLabel')}</legend>
          <div className="flex flex-wrap gap-2">
            {TUG_THEMES.map((theme) => {
              const on = themes.includes(theme.tag);
              return (
                <button
                  key={theme.tag}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggleTheme(theme.tag)}
                  className={`rounded-full border px-3 py-1.5 text-sm font-medium transition ${
                    on
                      ? 'border-emerald-400 bg-emerald-500/20 text-emerald-200'
                      : 'border-white/20 bg-slate-900/50 text-white/70 hover:border-white/50'
                  }`}
                >
                  {t(`themes.${theme.tag}`)}
                </button>
              );
            })}
          </div>
        </fieldset>

        <button
          type="submit"
          disabled={loading}
          className="mt-7 flex w-full items-center justify-center gap-3 rounded-xl bg-gradient-to-r from-blue-500 to-orange-500 px-6 py-4 text-xl font-black tracking-wide shadow-lg transition hover:brightness-110 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-70"
        >
          {loading && (
            <span
              className="h-5 w-5 animate-spin rounded-full border-2 border-white/40 border-t-white"
              aria-hidden
            />
          )}
          {loading ? t('loading') : t('start')}
        </button>
      </form>

      <div className="w-full rounded-2xl border border-white/10 bg-white/5 p-6 text-white/80">
        <h2 className="mb-2 text-sm font-bold uppercase tracking-wider text-white/50">{t('howToTitle')}</h2>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {howLines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
