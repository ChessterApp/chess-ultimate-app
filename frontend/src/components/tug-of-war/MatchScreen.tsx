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
 * In You vs Chesster mode (`bot` set) side B is played by useTugBot: the human
 * gets the large board, the zebra a small live board with a thinking pulse,
 * and a 5-minute cap ends the match on rope advantage.
 */

'use client';

import { useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { motion, AnimatePresence } from 'framer-motion';
import TugBoard from './TugBoard';
import RopeScene from './RopeScene';
import BotBoard from './BotBoard';
import { currentPuzzle, MAX_WRONG_ATTEMPTS, ROPE_LIMIT } from '@/lib/tug-of-war/gameReducer';
import type { GameState, GameAction } from '@/lib/tug-of-war/gameReducer';
import type { TeamSide } from '@/lib/tug-of-war/types';
import { TugSound, loadMuted, saveMuted } from '@/lib/tug-of-war/sound';
import { fireWinConfetti, resetConfetti } from '@/lib/tug-of-war/confetti';
import { track, ANALYTICS_EVENTS } from '@/lib/analytics/events';
import { BOT_MATCH_MS, type BotLevel } from '@/lib/tug-of-war/bot';
import { useTugBot, type BotView } from '@/lib/tug-of-war/useTugBot';

const ZEBRA_SRC = '/static/images/chesster-logo-v3.png';

type Feedback = 'idle' | 'correct' | 'wrong';

interface MatchScreenProps {
  state: GameState;
  dispatch: (action: GameAction) => void;
  /** Set in You vs Chesster mode: the zebra rank playing side B. */
  bot?: BotLevel;
}

function AttemptDots({ used }: { used: number }) {
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

function MuteButton({ muted, onToggle }: { muted: boolean; onToggle: () => void }) {
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

const shakeAnim = { x: [0, -10, 10, -7, 7, -3, 0] };
const flashAnim = {
  boxShadow: [
    '0 0 0px 0px rgba(34,197,94,0)',
    '0 0 32px 6px rgba(34,197,94,0.75)',
    '0 0 0px 0px rgba(34,197,94,0)',
  ],
};

export default function MatchScreen({ state, dispatch, bot }: MatchScreenProps) {
  const t = useTranslations('tugOfWar');
  const [feedbackA, setFeedbackA] = useState<Feedback>('idle');
  const [feedbackB, setFeedbackB] = useState<Feedback>('idle');
  const [skipToast, setSkipToast] = useState<{ A: boolean; B: boolean }>({ A: false, B: false });
  const [muted, setMuted] = useState(false);

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
      // Side only — team names are typed by kids and never leave the device.
      track(
        ANALYTICS_EVENTS.TUG_OF_WAR_FINISHED,
        bot
          ? { winner_side: state.winner, mode: 'bot', botLevel: bot.id }
          : { winner_side: state.winner },
      );
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

  const winnerName = state.winner === 'A' ? state.teamAName : state.teamBName;

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
          {bot && <MatchClock remainingMs={Math.max(0, BOT_MATCH_MS - elapsed)} />}
          <MuteButton muted={muted} onToggle={toggleMute} />
        </div>
        {bot ? (
          <BotHeader bot={bot} name={state.teamBName} score={state.boardB.solved} />
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
            name={state.teamBName}
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
            {bot && Math.abs(state.rope) < ROPE_LIMIT && (
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
              {!bot
                ? t('wins', { team: winnerName })
                : state.winner === 'A'
                  ? t('bot.youWin', { rank: state.teamBName })
                  : state.winner === 'B'
                    ? t('bot.botWins')
                    : t('bot.draw')}
            </motion.h2>
            {bot && state.winner === 'B' && (
              <p className="px-4 text-center text-xl font-semibold text-white drop-shadow-[0_2px_10px_rgba(0,0,0,0.85)]">
                {t('bot.tryAgain')}
              </p>
            )}
            <button
              onClick={() => dispatch({ type: 'REMATCH' })}
              className="pointer-events-auto rounded-xl bg-white px-8 py-4 text-xl font-black text-slate-900 shadow-lg transition hover:brightness-95 active:scale-95"
            >
              {t('rematch')}
            </button>
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

function MatchClock({ remainingMs }: { remainingMs: number }) {
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

function BotHeader({ bot, name, score }: { bot: BotLevel; name: string; score: number }) {
  return (
    <div className="flex items-center gap-3 text-right">
      <div>
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
