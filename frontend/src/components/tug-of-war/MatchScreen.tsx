/**
 * MatchScreen — the live 16:9 smartboard layout: top score bar, rope zone,
 * two boards with per-board feedback (green flash / red shake / skip toast),
 * and the win overlay with a Rematch button.
 *
 * The whole screen is sized off the viewport so it fits any 16:9 display
 * (1280×720 → 3840×2160) with zero scrolling — boards scale from the row's
 * available height, the rope scene stays ~26vh, and the container clips rather
 * than scrolls. Audio and confetti are fired here as side-effects of game
 * events; the reducer stays pure.
 *
 * In You vs Chesster mode (`bot` set) side B is played by useTugBot and a
 * 5-minute cap ends the match on rope advantage. At md+ the bot match renders
 * as ArenaMatch (scoreboard rope band + face-off boards); on mobile the human
 * gets the full board and the zebra a thin strip with a thinking pulse. In Adaptive mode
 * (`adaptive` set) the zebra's rank moves during the match — a small level meter
 * next to the badge shows it — and the end screen reports the player's level.
 */

'use client';

import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { useTranslations } from 'next-intl';
import { motion, AnimatePresence } from 'framer-motion';
import TugBoard from './TugBoard';
import RopeScene from './RopeScene';
import BotBoard from './BotBoard';
import ArenaMatch from './ArenaMatch';
import {
  AttemptDots,
  LevelMeter,
  MatchClock,
  MatchResult,
  MuteButton,
  ZEBRA_SRC,
  flashAnim,
  shakeAnim,
  type Feedback,
} from './matchParts';
import { currentPuzzle } from '@/lib/tug-of-war/gameReducer';
import type { GameState, GameAction } from '@/lib/tug-of-war/gameReducer';
import type { TeamSide } from '@/lib/tug-of-war/types';
import { TugSound, loadMuted, saveMuted } from '@/lib/tug-of-war/sound';
import { fireWinConfetti, resetConfetti } from '@/lib/tug-of-war/confetti';
import { track, ANALYTICS_EVENTS } from '@/lib/analytics/events';
import { BOT_MATCH_MS, type BotLevel } from '@/lib/tug-of-war/bot';
import { useTugBot, type BotView } from '@/lib/tug-of-war/useTugBot';
import type { AdaptiveView } from '@/lib/tug-of-war/useAdaptiveBot';

/** Tailwind `md` — the Arena layout's breakpoint. */
const MD_QUERY = '(min-width: 768px)';

function subscribeMd(onChange: () => void) {
  if (typeof window.matchMedia !== 'function') return () => {};
  const mql = window.matchMedia(MD_QUERY);
  mql.addEventListener('change', onChange);
  return () => mql.removeEventListener('change', onChange);
}

/** md+ viewport; defaults to desktop where matchMedia is unavailable. */
function useIsMdUp() {
  return useSyncExternalStore(
    subscribeMd,
    () => (typeof window.matchMedia === 'function' ? window.matchMedia(MD_QUERY).matches : true),
    () => true,
  );
}

interface MatchScreenProps {
  state: GameState;
  dispatch: (action: GameAction) => void;
  /** Set in You vs Chesster mode: the zebra rank playing side B. */
  bot?: BotLevel;
  /** Set in Adaptive mode (then `bot` is the adaptive ladder's current level). */
  adaptive?: AdaptiveView;
  /** End-screen Rematch; defaults to back-to-setup. */
  onRematch?: () => void;
  /** Adaptive end screen: back to setup to pick a fixed rank. */
  onTryFixed?: () => void;
}

export default function MatchScreen({
  state,
  dispatch,
  bot,
  adaptive,
  onRematch = () => dispatch({ type: 'REMATCH' }),
  onTryFixed,
}: MatchScreenProps) {
  const t = useTranslations('tugOfWar');
  const [feedbackA, setFeedbackA] = useState<Feedback>('idle');
  const [feedbackB, setFeedbackB] = useState<Feedback>('idle');
  const [skipToast, setSkipToast] = useState<{ A: boolean; B: boolean }>({ A: false, B: false });
  const [muted, setMuted] = useState(false);
  const isMdUp = useIsMdUp();

  const over = state.phase === 'over';
  const puzzleA = currentPuzzle(state.boardA);
  const puzzleB = currentPuzzle(state.boardB);

  // Client-only sound player, seeded from the persisted mute preference. Read
  // after mount (not in a lazy initializer) so SSR and first client render
  // agree — localStorage is unavailable on the server.
  const soundRef = useRef<TugSound | null>(null);
  useEffect(() => {
    const initial = loadMuted();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMuted(initial);
    soundRef.current = new TugSound(initial);
    return () => {
      soundRef.current = null;
    };
  }, []);

  // Unlock audio on the first user gesture. iOS/Safari only unlock playback
  // (both Web Audio and <audio>) from inside a real pointer/touch/key handler,
  // so prime the shared context here — otherwise the correct-move cue that fires
  // from the opponent-reply timer, and the win fanfare, stay silent. WebKit
  // often does NOT unlock on the first pointerdown, so keep listening (pointer,
  // touch, click, key) until unlock() reports the context is actually running.
  useEffect(() => {
    const events: (keyof WindowEventMap)[] = ['pointerdown', 'touchend', 'click', 'keydown'];
    const detach = () => events.forEach((e) => window.removeEventListener(e, unlock));
    const unlock = () => {
      if (soundRef.current?.unlock()) detach();
    };
    events.forEach((e) => window.addEventListener(e, unlock));
    return detach;
  }, []);

  const toggleMute = () => {
    setMuted((m) => {
      const next = !m;
      saveMuted(next);
      soundRef.current?.setMuted(next);
      return next;
    });
  };

  // Fire the win fanfare + confetti once, on the match→over transition; clear
  // the confetti canvas whenever we leave the over phase (rematch) or unmount.
  const prevOver = useRef(false);
  useEffect(() => {
    if (over && !prevOver.current) {
      // Against Chesster only the human's win is celebrated.
      if (state.winner && (!bot || state.winner === 'A')) {
        soundRef.current?.win();
        fireWinConfetti(state.winner).catch(() => {});
      }
    }
    if (!over && prevOver.current) {
      resetConfetti().catch(() => {});
    }
    prevOver.current = over;
  }, [over, state.winner, bot]);

  // Report the finish once — in Adaptive mode only after the final estimate is in.
  const reported = useRef(false);
  const result = adaptive?.result;
  useEffect(() => {
    if (!over || reported.current || (adaptive && !result)) return;
    reported.current = true;
    // Side only — team names are typed by kids and never leave the device.
    track(
      ANALYTICS_EVENTS.TUG_OF_WAR_FINISHED,
      !bot
        ? { winner_side: state.winner }
        : result
          ? {
              winner_side: state.winner,
              mode: 'bot',
              botMode: 'adaptive',
              botLevel: bot.id,
              estimate: result.estimate,
              avgSeconds: result.avgSeconds,
              peakBotLevel: result.peakBotLevel,
            }
          : { winner_side: state.winner, mode: 'bot', botMode: 'static', botLevel: bot.id },
    );
  }, [over, adaptive, result, bot, state.winner]);

  useEffect(() => {
    return () => {
      resetConfetti().catch(() => {});
    };
  }, []);

  // Fire the "Skipped" toast whenever a board's auto-skip counter ticks up.
  const prevSkips = useRef({ A: state.boardA.skips, B: state.boardB.skips });
  useEffect(() => {
    const flash = (side: TeamSide) => {
      setSkipToast((t) => ({ ...t, [side]: true }));
      setTimeout(() => setSkipToast((t) => ({ ...t, [side]: false })), 1500);
    };
    if (state.boardA.skips > prevSkips.current.A) flash('A');
    if (state.boardB.skips > prevSkips.current.B) flash('B');
    prevSkips.current = { A: state.boardA.skips, B: state.boardB.skips };
  }, [state.boardA.skips, state.boardB.skips]);

  const makeHandlers = (
    team: TeamSide,
    setFeedback: (f: Feedback) => void,
  ) => ({
    onSolved: () => {
      setFeedback('correct');
      soundRef.current?.correctMove();
      dispatch({ type: 'SOLVE', team });
      setTimeout(() => setFeedback('idle'), 650);
    },
    onWrong: () => {
      setFeedback('wrong');
      soundRef.current?.wrongMove();
      dispatch({ type: 'WRONG', team });
      setTimeout(() => setFeedback('idle'), 550);
    },
  });

  const handlersA = makeHandlers('A', setFeedbackA);
  const handlersB = makeHandlers('B', setFeedbackB);

  const botView = useTugBot({
    level: bot ?? null,
    puzzle: bot ? puzzleB : null,
    round: state.boardB.index,
    active: !!bot && !over,
    ...handlersB,
  });

  // Bot-mode match clock: counts only while the tab is visible; at the cap the
  // reducer ends the match on rope advantage.
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!bot || over) return;
    const id = setInterval(() => {
      if (!document.hidden) setElapsed((e) => e + 1000);
    }, 1000);
    return () => clearInterval(id);
  }, [bot, over]);
  useEffect(() => {
    if (bot && !over && elapsed >= BOT_MATCH_MS) dispatch({ type: 'TIME_UP' });
  }, [bot, over, elapsed, dispatch]);

  // The adaptive zebra's name follows its current rank.
  const botName = adaptive && bot ? t(`bot.levels.${bot.id}`) : state.teamBName;
  const remainingMs = Math.max(0, BOT_MATCH_MS - elapsed);

  if (bot && isMdUp) {
    return (
      <ArenaMatch
        state={state}
        bot={bot}
        botName={botName}
        botView={botView}
        adaptive={adaptive}
        puzzleA={puzzleA}
        puzzleB={puzzleB}
        feedbackA={feedbackA}
        feedbackB={feedbackB}
        skipToast={skipToast}
        handlersA={handlersA}
        remainingMs={remainingMs}
        muted={muted}
        onToggleMute={toggleMute}
        onRematch={onRematch}
        onTryFixed={onTryFixed}
      />
    );
  }

  return (
    <div className="relative flex h-screen w-full flex-col gap-[1.2vh] overflow-hidden px-[2vw] py-[1.5vh] text-white">
      {/* Top bar */}
      <div className="flex shrink-0 items-center justify-between rounded-2xl border border-white/10 bg-white/5 px-5 py-2">
        <TeamHeader name={state.teamAName} score={state.boardA.solved} accent="blue" align="left" />
        <div className="flex flex-col items-center gap-1">
          <div className="text-[0.7rem] font-bold uppercase tracking-widest text-white/40">{t('ropeLabel')}</div>
          <div className="text-2xl font-black leading-none tabular-nums">
            {state.rope > 0 ? `+${state.rope}` : state.rope}
          </div>
          {bot && <MatchClock remainingMs={remainingMs} />}
          <MuteButton muted={muted} onToggle={toggleMute} />
        </div>
        {bot ? (
          <BotHeader
            bot={bot}
            name={botName}
            score={state.boardB.solved}
            meter={adaptive && <LevelMeter rating={bot.rating} trend={adaptive.state.trend} />}
          />
        ) : (
          <TeamHeader name={state.teamBName} score={state.boardB.solved} accent="orange" align="right" />
        )}
      </div>

      {/* Rope zone */}
      <div className="shrink-0">
        <RopeScene rope={state.rope} winner={state.winner} />
      </div>

      {/* Boards */}
      {bot ? (
        // Mobile: thin bot strip under the rope, human board fills the rest.
        // Desktop / smartboard: large human board, small bot column on the right.
        <div className="flex min-h-0 flex-1 flex-col gap-[1.2vh] md:flex-row md:items-stretch md:justify-center md:gap-[2vw]">
          <BoardPanel
            feedback={feedbackA}
            used={state.boardA.wrongAttempts}
            accent="blue"
            skip={skipToast.A}
          >
            {puzzleA && (
              <TugBoard puzzle={puzzleA} accent="blue" disabled={over} {...handlersA} />
            )}
          </BoardPanel>
          <BotPanel
            bot={bot}
            name={botName}
            view={botView}
            puzzleFen={puzzleB?.fen ?? botView.fen}
            feedback={feedbackB}
            used={state.boardB.wrongAttempts}
            skip={skipToast.B}
          />
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 items-stretch justify-center gap-[2vw]">
          <BoardPanel
            feedback={feedbackA}
            used={state.boardA.wrongAttempts}
            accent="blue"
            skip={skipToast.A}
          >
            {puzzleA && (
              <TugBoard puzzle={puzzleA} accent="blue" disabled={over} {...handlersA} />
            )}
          </BoardPanel>
          <BoardPanel
            feedback={feedbackB}
            used={state.boardB.wrongAttempts}
            accent="orange"
            skip={skipToast.B}
          >
            {puzzleB && (
              <TugBoard puzzle={puzzleB} accent="orange" disabled={over} {...handlersB} />
            )}
          </BoardPanel>
        </div>
      )}

      {/* Win overlay */}
      <AnimatePresence>
        {over && (
          <motion.div
            className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center gap-6"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <MatchResult
              state={state}
              isBot={!!bot}
              botName={botName}
              result={result}
              onRematch={onRematch}
              onTryFixed={adaptive ? onTryFixed : undefined}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function TeamHeader({
  name,
  score,
  accent,
  align,
}: {
  name: string;
  score: number;
  accent: 'blue' | 'orange';
  align: 'left' | 'right';
}) {
  const color = accent === 'blue' ? 'text-blue-300' : 'text-orange-300';
  return (
    <div className={align === 'right' ? 'text-right' : 'text-left'}>
      <div className={`text-lg font-bold sm:text-2xl ${color}`}>{name}</div>
      <div className="text-3xl font-black leading-none tabular-nums sm:text-4xl">{score}</div>
    </div>
  );
}

function BoardPanel({
  children,
  feedback,
  used,
  accent,
  skip,
}: {
  children: React.ReactNode;
  feedback: Feedback;
  used: number;
  accent: 'blue' | 'orange';
  skip: boolean;
}) {
  const t = useTranslations('tugOfWar');
  return (
    <div className="relative flex h-full min-h-0 flex-1 flex-col items-center justify-center gap-[0.8vh]">
      <div className="flex min-h-0 w-full flex-1 items-center justify-center">
        <motion.div
          className="aspect-square h-full min-w-0 max-h-full max-w-full rounded-xl"
          animate={
            feedback === 'wrong' ? shakeAnim : feedback === 'correct' ? flashAnim : {}
          }
          transition={{ duration: feedback === 'wrong' ? 0.45 : 0.6 }}
        >
          {children}
        </motion.div>
      </div>
      <AttemptDots used={used} />
      <AnimatePresence>
        {skip && (
          <motion.div
            className={`absolute -top-1 rounded-full px-4 py-1.5 text-sm font-bold shadow-lg ${
              accent === 'blue' ? 'bg-blue-500' : 'bg-orange-500'
            }`}
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
          >
            {t('skipped')}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function BotHeader({
  bot,
  name,
  score,
  meter,
}: {
  bot: BotLevel;
  name: string;
  score: number;
  meter?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3 text-right">
      <div className="flex flex-col items-end">
        {meter}
        <div
          className="inline-block rounded-full px-2.5 py-0.5 text-xs font-black uppercase tracking-wide text-slate-950 sm:text-sm"
          style={{ backgroundColor: bot.color }}
          data-testid="tug-bot-rank"
        >
          {name}
        </div>
        <div className="mt-1 text-3xl font-black leading-none tabular-nums sm:text-4xl">{score}</div>
      </div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={ZEBRA_SRC}
        alt=""
        aria-hidden="true"
        draggable={false}
        className="hidden h-12 w-12 rounded-full bg-white p-0.5 sm:block"
        style={{ boxShadow: `0 0 0 3px ${bot.color}` }}
      />
    </div>
  );
}

function BotPanel({
  bot,
  name,
  view,
  puzzleFen,
  feedback,
  used,
  skip,
}: {
  bot: BotLevel;
  name: string;
  view: BotView;
  puzzleFen: string;
  feedback: Feedback;
  used: number;
  skip: boolean;
}) {
  const t = useTranslations('tugOfWar');
  return (
    <div className="relative order-first flex shrink-0 items-center gap-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 md:order-none md:w-[20vw] md:max-w-[360px] md:flex-col md:justify-center md:gap-[1.2vh] md:p-4">
      <div className="flex items-center gap-2 md:flex-col">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={ZEBRA_SRC}
          alt=""
          aria-hidden="true"
          draggable={false}
          className={`h-10 w-10 rounded-full bg-white p-0.5 md:h-16 md:w-16 ${view.thinking ? 'animate-pulse' : ''}`}
          style={{ boxShadow: `0 0 0 3px ${bot.color}` }}
        />
        <div className="flex flex-col md:items-center">
          <span className="text-sm font-bold text-white/90 md:hidden">{name}</span>
          <span
            aria-live="polite"
            className={`text-xs font-semibold text-white/60 transition-opacity ${view.thinking ? 'opacity-100' : 'opacity-0'}`}
          >
            {t('bot.thinking')}
          </span>
        </div>
      </div>
      <motion.div
        className="ml-auto w-[18vw] max-w-[96px] rounded-lg md:ml-0 md:w-full md:max-w-none"
        animate={feedback === 'wrong' ? shakeAnim : feedback === 'correct' ? flashAnim : {}}
        transition={{ duration: feedback === 'wrong' ? 0.45 : 0.6 }}
      >
        {view.fen && <BotBoard fen={view.fen} lastMove={view.lastMove} puzzleFen={puzzleFen} />}
      </motion.div>
      <div className="hidden md:block">
        <AttemptDots used={used} />
      </div>
      <AnimatePresence>
        {skip && (
          <motion.div
            className="absolute -top-1 left-1/2 -translate-x-1/2 rounded-full bg-orange-500 px-4 py-1.5 text-sm font-bold shadow-lg"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
          >
            {t('skipped')}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

