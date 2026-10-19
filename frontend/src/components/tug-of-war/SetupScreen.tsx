/**
 * SetupScreen — pick a mode first. Team vs Team: team names, difficulty band
 * and theme picker, then Start. You vs Chesster: tapping one of six zebra rank
 * cards starts the match straight away, on the puzzle band of that rank.
 * Selections drive the live puzzle prefetch (see lib/tug-of-war/prefetch.ts).
 */

'use client';

import { useState } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import { TUG_LEVELS, TUG_THEMES, type TugLevel } from '@/lib/tug-of-war/prefetch';
import { BOT_LEVELS, botPuzzleLevel, type BotLevel, type BotLevelId } from '@/lib/tug-of-war/bot';

const ZEBRA_SRC = '/static/images/chesster-logo-v3.png';
const FASTEST_SECONDS = Math.min(...BOT_LEVELS.map((l) => l.secondsPerMove));

export interface StartConfig {
  teamA: string;
  teamB: string;
  level: TugLevel;
  themes: string[];
  /** Set in You vs Chesster mode: the zebra rank playing side B. */
  bot?: BotLevelId;
}

interface SetupScreenProps {
  initialTeamA: string;
  initialTeamB: string;
  onStart: (config: StartConfig) => void;
  loading?: boolean;
  /** Last bot rank played; opens the setup in You vs Chesster mode. */
  initialBot?: BotLevelId | null;
}

export default function SetupScreen({
  initialTeamA,
  initialTeamB,
  onStart,
  loading = false,
  initialBot = null,
}: SetupScreenProps) {
  const t = useTranslations('tugOfWar');
  const locale = useLocale();
  const [teamA, setTeamA] = useState(initialTeamA);
  const [teamB, setTeamB] = useState(initialTeamB);
  const [level, setLevel] = useState<TugLevel>('knight');
  const [themes, setThemes] = useState<string[]>([]);
  const [mode, setMode] = useState<'team' | 'bot'>(initialBot ? 'bot' : 'team');
  const [pickedBot, setPickedBot] = useState<BotLevelId | null>(initialBot);

  const startBot = (l: BotLevel) => {
    if (loading) return;
    setPickedBot(l.id);
    onStart({
      teamA: t('bot.you'),
      teamB: t(`bot.levels.${l.id}`),
      level: botPuzzleLevel(l),
      themes: [],
      bot: l.id,
    });
  };

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

      <div role="radiogroup" aria-label={t('mode.label')} className="grid w-full grid-cols-2 gap-3">
        {(['team', 'bot'] as const).map((m) => (
          <button
            key={m}
            type="button"
            role="radio"
            aria-checked={mode === m}
            onClick={() => setMode(m)}
            className={`rounded-2xl border px-4 py-3 text-left transition ${
              mode === m
                ? 'border-white bg-white text-slate-900'
                : 'border-white/15 bg-white/5 text-white hover:border-white/40'
            }`}
          >
            <span className="block text-lg font-black leading-tight">{t(`mode.${m}.title`)}</span>
            <span className={`mt-0.5 block text-sm ${mode === m ? 'text-slate-600' : 'text-white/60'}`}>
              {t(`mode.${m}.desc`)}
            </span>
          </button>
        ))}
      </div>

      {mode === 'bot' ? (
        <section className="w-full rounded-2xl border border-white/10 bg-white/5 p-6 sm:p-8">
          <h2 className="mb-3 text-sm font-semibold text-white/70">{t('bot.chooseRank')}</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {BOT_LEVELS.map((l) => (
              <ZebraCard
                key={l.id}
                level={l}
                name={t(`bot.levels.${l.id}`)}
                rating={t('bot.rating', { rating: l.rating })}
                speedLabel={t('bot.speed')}
                busy={loading && pickedBot === l.id}
                disabled={loading}
                onPick={() => startBot(l)}
              />
            ))}
          </div>
        </section>
      ) : (
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
      )}

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

function ZebraCard({
  level,
  name,
  rating,
  speedLabel,
  busy,
  disabled,
  onPick,
}: {
  level: BotLevel;
  name: string;
  rating: string;
  speedLabel: string;
  busy: boolean;
  disabled: boolean;
  onPick: () => void;
}) {
  const speed = Math.round((FASTEST_SECONDS / level.secondsPerMove) * 100);
  return (
    <button
      type="button"
      onClick={onPick}
      disabled={disabled}
      data-testid={`zebra-${level.id}`}
      className="group flex flex-col items-center gap-2 rounded-xl border border-white/15 bg-slate-900/50 p-3 text-center transition hover:border-white/50 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
    >
      <span
        className="relative flex h-16 w-16 items-center justify-center rounded-full bg-white p-1 sm:h-20 sm:w-20"
        style={{ boxShadow: `0 0 0 4px ${level.color}` }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={ZEBRA_SRC} alt="" aria-hidden="true" className="h-full w-full object-contain" draggable={false} />
        {busy && (
          <span
            className="absolute inset-0 animate-spin rounded-full border-2 border-transparent border-t-white"
            aria-hidden
          />
        )}
      </span>
      <span
        className="rounded-full px-2.5 py-0.5 text-xs font-black uppercase tracking-wide text-slate-950"
        style={{ backgroundColor: level.color }}
      >
        {name}
      </span>
      <span className="text-sm font-semibold tabular-nums text-white/80">{rating}</span>
      <span className="flex w-full items-center gap-2 text-[0.65rem] font-semibold uppercase tracking-wider text-white/50">
        {speedLabel}
        <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/10">
          <span className="block h-full rounded-full" style={{ width: `${speed}%`, backgroundColor: level.color }} />
        </span>
      </span>
    </button>
  );
}
