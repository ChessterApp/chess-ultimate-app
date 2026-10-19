/**
 * Shared Tug of War match UI pieces used by both the classic MatchScreen
 * layout and the bot-mode Arena: attempt dots, mute toggle, match clock,
 * feedback animations, the adaptive level meter and the end-screen result.
 */

'use client';

import { useTranslations } from 'next-intl';
import { motion, useReducedMotion } from 'framer-motion';
import { MAX_WRONG_ATTEMPTS, ROPE_LIMIT } from '@/lib/tug-of-war/gameReducer';
import type { GameState } from '@/lib/tug-of-war/gameReducer';
import { BOT_LEVELS } from '@/lib/tug-of-war/bot';
import { rankNumber, type AdaptiveState, type SavedAdaptive } from '@/lib/tug-of-war/adaptive';

export const ZEBRA_SRC = '/static/images/chesster-logo-v3.png';

export type Feedback = 'idle' | 'correct' | 'wrong';

export function AttemptDots({ used }: { used: number }) {
  const t = useTranslations('tugOfWar');
  return (
    <div
      className="flex items-center gap-1"
      aria-label={t('wrongAria', { used, max: MAX_WRONG_ATTEMPTS })}
    >
      {Array.from({ length: MAX_WRONG_ATTEMPTS }).map((_, i) => (
        <span
          key={i}
          className={`h-[1.4vh] w-[1.4vh] max-h-2.5 max-w-2.5 rounded-full ${i < used ? 'bg-red-500' : 'bg-white/25'}`}
        />
      ))}
    </div>
  );
}

export function MuteButton({ muted, onToggle }: { muted: boolean; onToggle: () => void }) {
  const t = useTranslations('tugOfWar');
  const label = muted ? t('muteOff') : t('muteOn');
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={muted}
      aria-label={label}
      title={label}
      className="flex h-9 w-9 items-center justify-center rounded-full border border-white/15 bg-white/5 text-white/80 transition hover:bg-white/10 active:scale-95"
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M4 9v6h4l5 4V5L8 9H4z"
          fill="currentColor"
        />
        {muted ? (
          <path d="M16 9l5 6M21 9l-5 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        ) : (
          <path
            d="M16 8.5a4 4 0 010 7M18.5 6a7 7 0 010 12"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            fill="none"
          />
        )}
      </svg>
    </button>
  );
}

export const shakeAnim = { x: [0, -10, 10, -7, 7, -3, 0] };
export const flashAnim = {
  boxShadow: [
    '0 0 0px 0px rgba(34,197,94,0)',
    '0 0 32px 6px rgba(34,197,94,0.75)',
    '0 0 0px 0px rgba(34,197,94,0)',
  ],
};

export function MatchClock({ remainingMs }: { remainingMs: number }) {
  const t = useTranslations('tugOfWar');
  const total = Math.ceil(remainingMs / 1000);
  const mm = Math.floor(total / 60);
  const ss = String(total % 60).padStart(2, '0');
  return (
    <div
      aria-label={t('bot.timeLeft')}
      title={t('bot.timeLeft')}
      className={`text-sm font-bold leading-none tabular-nums ${total <= 30 ? 'text-red-400' : 'text-white/70'}`}
    >
      {mm}:{ss}
    </div>
  );
}

/** Adaptive mode: "Lv 4 ↑" plus six rank pips; the number slides in on a change. */
export function LevelMeter({ rating, trend }: { rating: number; trend: AdaptiveState['trend'] }) {
  const t = useTranslations('tugOfWar');
  const reduce = useReducedMotion();
  const lv = rankNumber(rating);
  const color = BOT_LEVELS[lv - 1].color;
  const offset = reduce || !trend ? 0 : trend === 'up' ? 8 : -8;
  return (
    <div
      data-testid="tug-level-meter"
      aria-label={t('adaptive.meterAria', { level: lv, max: BOT_LEVELS.length })}
      className="mb-1 flex items-center gap-1.5 text-[0.7rem] font-bold uppercase tracking-wider text-white/60"
    >
      <motion.span
        key={lv}
        className="tabular-nums text-white/90"
        initial={{ opacity: reduce ? 1 : 0, y: offset }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: reduce ? 0 : 0.35 }}
      >
        {t('adaptive.level', { level: lv })}
        {trend && (
          <span aria-hidden="true" className={trend === 'up' ? 'ml-0.5 text-emerald-300' : 'ml-0.5 text-red-300'}>
            {trend === 'up' ? '↑' : '↓'}
          </span>
        )}
      </motion.span>
      <span className="flex gap-0.5" aria-hidden="true">
        {BOT_LEVELS.map((l, i) => (
          <span
            key={l.id}
            className="h-1.5 w-2.5 rounded-full transition-colors duration-300 motion-reduce:transition-none"
            style={{ backgroundColor: i < lv ? color : 'rgba(255,255,255,0.15)' }}
          />
        ))}
      </span>
    </div>
  );
}

/** Adaptive end screen: the player's level, speed and the best zebra rank beaten. */
export function AdaptiveSummary({ result }: { result: SavedAdaptive }) {
  const t = useTranslations('tugOfWar');
  const parts = [t('adaptive.result.level', { rating: result.estimate })];
  if (result.avgSeconds !== null) {
    parts.push(t('adaptive.result.speed', { seconds: Math.round(result.avgSeconds) }));
  }
  parts.push(
    t('adaptive.result.peak', {
      rank: result.peakBotLevel ? t(`bot.levels.${result.peakBotLevel}`) : t('adaptive.result.noPeak'),
    }),
  );
  return (
    <p
      data-testid="tug-adaptive-summary"
      className="mx-4 rounded-2xl bg-slate-900/85 px-5 py-3 text-center text-base font-semibold text-white shadow-lg sm:text-lg"
    >
      {parts.join(' · ')}
    </p>
  );
}

/**
 * End-screen result: time-up pill, headline, try-again hint, adaptive summary
 * and the Rematch / Try a fixed level buttons. Shared by the classic overlay
 * and the Arena's result card.
 */
export function MatchResult({
  state,
  isBot,
  botName,
  result,
  onRematch,
  onTryFixed,
}: {
  state: GameState;
  isBot: boolean;
  botName: string;
  result?: SavedAdaptive | null;
  onRematch: () => void;
  onTryFixed?: () => void;
}) {
  const t = useTranslations('tugOfWar');
  const winnerName = state.winner === 'A' ? state.teamAName : state.teamBName;
  return (
    <>
      {isBot && Math.abs(state.rope) < ROPE_LIMIT && (
        <div className="rounded-full bg-slate-900/80 px-4 py-1 text-sm font-bold uppercase tracking-widest text-white/80">
          {t('bot.timeUp')}
        </div>
      )}
      <motion.h2
        className={`px-4 text-center text-5xl font-black tracking-tight drop-shadow-[0_2px_14px_rgba(0,0,0,0.85)] sm:text-6xl ${
          state.winner === 'A' ? 'text-blue-400' : state.winner === 'B' ? 'text-red-400' : 'text-white'
        }`}
        initial={{ scale: 0.6, y: 20 }}
        animate={{ scale: 1, y: 0 }}
        transition={{ type: 'spring', stiffness: 200, damping: 12 }}
      >
        {!isBot
          ? t('wins', { team: winnerName })
          : state.winner === 'A'
            ? t('bot.youWin', { rank: botName })
            : state.winner === 'B'
              ? t('bot.botWins')
              : t('bot.draw')}
      </motion.h2>
      {isBot && state.winner === 'B' && (
        <p className="px-4 text-center text-xl font-semibold text-white drop-shadow-[0_2px_10px_rgba(0,0,0,0.85)]">
          {t('bot.tryAgain')}
        </p>
      )}
      {result && <AdaptiveSummary result={result} />}
      <div className="pointer-events-auto flex flex-wrap items-center justify-center gap-3">
        <button
          onClick={onRematch}
          className="rounded-xl bg-white px-8 py-4 text-xl font-black text-slate-900 shadow-lg transition hover:brightness-95 active:scale-95"
        >
          {t('rematch')}
        </button>
        {onTryFixed && (
          <button
            onClick={onTryFixed}
            className="rounded-xl border border-white/30 bg-slate-900/80 px-6 py-4 text-lg font-bold text-white shadow-lg transition hover:bg-slate-800 active:scale-95"
          >
            {t('adaptive.tryFixed')}
          </button>
        )}
      </div>
    </>
  );
}
