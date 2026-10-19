/**
 * ArenaMatch — the md+ You vs Chesster layout ("The Arena"): a dark
 * scoreboard band with the rope track across it (you left, the zebra right,
 * timer above the knot), and a face-off below — the human board with a blue
 * glow, the zebra's board ~75% of its size in red, "VS" between.
 *
 * Purely presentational: MatchScreen owns the game logic (handlers, bot,
 * clock, sound, confetti, analytics) and passes the results down. The Arena
 * only adds cause→effect polish: a "+1" flies from the solving board to the
 * knot, and a "Zebra missed" toast flashes on the bot's wrong moves.
 */

'use client';

import { useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import TugBoard from './TugBoard';
import BotBoard from './BotBoard';
import ArenaRope from './ArenaRope';
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
import type { GameState } from '@/lib/tug-of-war/gameReducer';
import type { TeamSide, TugPuzzle } from '@/lib/tug-of-war/types';
import type { BotLevel } from '@/lib/tug-of-war/bot';
import type { BotView } from '@/lib/tug-of-war/useTugBot';
import type { AdaptiveView } from '@/lib/tug-of-war/useAdaptiveBot';
import { orientationFromFen } from '@/lib/tug-of-war/orientation';

/** Human board edge: fits under the band at 16:9 and beside the zebra at 4:3. */
const BOARD = 'min(64vh, 44vw)';
const BOT_BOARD = 'calc(min(64vh, 44vw) * 0.75)';

interface Handlers {
  onSolved: () => void;
  onWrong: () => void;
}

interface Flier {
  id: number;
  side: TeamSide;
  from: { x: number; y: number };
  to: { x: number; y: number };
}

export interface ArenaMatchProps {
  state: GameState;
  bot: BotLevel;
  botName: string;
  botView: BotView;
  adaptive?: AdaptiveView;
  puzzleA: TugPuzzle | null;
  puzzleB: TugPuzzle | null;
  feedbackA: Feedback;
  feedbackB: Feedback;
  skipToast: { A: boolean; B: boolean };
  handlersA: Handlers;
  remainingMs: number;
  muted: boolean;
  onToggleMute: () => void;
  onRematch: () => void;
  onTryFixed?: () => void;
}

export default function ArenaMatch({
  state,
  bot,
  botName,
  botView,
  adaptive,
  puzzleA,
  puzzleB,
  feedbackA,
  feedbackB,
  skipToast,
  handlersA,
  remainingMs,
  muted,
  onToggleMute,
  onRematch,
  onTryFixed,
}: ArenaMatchProps) {
  const t = useTranslations('tugOfWar');
  const reduce = useReducedMotion();
  const over = state.phase === 'over';
  const solvedA = state.boardA.solved;
  const solvedB = state.boardB.solved;

  const rootRef = useRef<HTMLDivElement>(null);
  const knotRef = useRef<HTMLDivElement>(null);
  const humanRef = useRef<HTMLDivElement>(null);
  const zebraRef = useRef<HTMLDivElement>(null);

  // A "+1" flies from the board that just solved to the knot.
  const [fliers, setFliers] = useState<Flier[]>([]);
  const prevSolved = useRef({ A: solvedA, B: solvedB });
  const nextId = useRef(0);
  useEffect(() => {
    const prev = prevSolved.current;
    prevSolved.current = { A: solvedA, B: solvedB };
    if (reduce) return;
    const root = rootRef.current?.getBoundingClientRect();
    const knot = knotRef.current?.getBoundingClientRect();
    if (!root || !knot) return;
    const centre = (r: DOMRect) => ({ x: r.left + r.width / 2 - root.left, y: r.top + r.height / 2 - root.top });
    const spawn = (side: TeamSide, el: HTMLDivElement | null) => {
      if (!el) return;
      const r = el.getBoundingClientRect();
      const id = nextId.current++;
      const from = { x: r.left + r.width / 2 - root.left, y: r.top + r.height * 0.25 - root.top };
      setFliers((f) => [...f, { id, side, from, to: centre(knot) }]);
      setTimeout(() => setFliers((f) => f.filter((x) => x.id !== id)), 900);
    };
    if (solvedA > prev.A) spawn('A', humanRef.current);
    if (solvedB > prev.B) spawn('B', zebraRef.current);
  }, [solvedA, solvedB, reduce]);

  // Short red "Zebra missed" toast on each of the bot's wrong moves.
  // feedbackB flips back to idle after ~0.5s, so the hide timer lives in a ref
  // rather than the effect cleanup (which would cancel it on that flip).
  const [missed, setMissed] = useState(false);
  const missedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (feedbackB !== 'wrong') return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMissed(true);
    if (missedTimer.current) clearTimeout(missedTimer.current);
    missedTimer.current = setTimeout(() => setMissed(false), 1300);
  }, [feedbackB]);
  useEffect(() => () => {
    if (missedTimer.current) clearTimeout(missedTimer.current);
  }, []);

  const toMove = puzzleA && orientationFromFen(puzzleA.fen) === 'black' ? t('bot.blackToMove') : t('bot.whiteToMove');
  const initial = (state.teamAName.trim()[0] ?? 'A').toUpperCase();

  return (
    <div
      ref={rootRef}
      data-testid="tug-arena"
      className="relative flex h-screen w-full flex-col gap-[2vh] overflow-hidden bg-[#0b1020] px-[2vw] py-[1.5vh] text-white"
    >
      {/* Scoreboard rope band */}
      <div
        className="relative flex h-[18vh] min-h-[110px] shrink-0 items-center gap-[2vw] rounded-3xl border border-white/10 px-[2vw]"
        style={{
          background:
            'linear-gradient(90deg, rgba(37,99,235,0.35) 0%, rgba(15,23,42,0) 22%, rgba(15,23,42,0) 78%, rgba(220,38,38,0.32) 100%), #0f172a',
        }}
      >
        <div className="flex shrink-0 items-center gap-[1vw]">
          <div className="flex h-[9vh] w-[9vh] items-center justify-center rounded-full bg-gradient-to-br from-blue-400 to-blue-700 text-[4vh] font-black shadow-[0_0_0_4px_rgba(59,130,246,0.35)]">
            {initial}
          </div>
          <div className="leading-none">
            <div className="text-[1.8vh] font-bold uppercase tracking-[0.2em] text-blue-300">{state.teamAName}</div>
            <div className="mt-[0.6vh] text-[6vh] font-black tabular-nums">{solvedA}</div>
          </div>
        </div>

        <div className="flex min-w-0 flex-1 flex-col items-center gap-[0.8vh]">
          <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1">
            <MatchClock remainingMs={remainingMs} />
            <MuteButton muted={muted} onToggle={onToggleMute} />
          </div>
          <ArenaRope rope={state.rope} pulls={solvedA + solvedB} knotRef={knotRef} />
        </div>

        <div className="flex shrink-0 items-center gap-[1vw]">
          <div className="flex flex-col items-end leading-none">
            {adaptive && <LevelMeter rating={bot.rating} trend={adaptive.state.trend} />}
            <div
              className="rounded-full px-3 py-1 text-[1.6vh] font-black uppercase tracking-wide text-slate-950"
              style={{ backgroundColor: bot.color }}
              data-testid="tug-bot-rank"
            >
              {botName}
            </div>
            <div className="mt-[0.6vh] text-[6vh] font-black tabular-nums">{solvedB}</div>
          </div>
          <div className="relative h-[10vh] w-[10vh]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={ZEBRA_SRC}
              alt=""
              aria-hidden="true"
              draggable={false}
              className="h-full w-full rounded-full bg-white p-[0.6vh]"
              style={{ boxShadow: `0 0 0 3px ${bot.color}55` }}
            />
            {botView.thinking && (
              <svg
                data-testid="tug-arena-thinking-ring"
                aria-hidden="true"
                viewBox="0 0 100 100"
                className="absolute -inset-[0.6vh] animate-spin motion-reduce:animate-none"
                style={{ animationDuration: '1.4s' }}
              >
                <circle cx="50" cy="50" r="47" fill="none" stroke={bot.color} strokeWidth="5" strokeLinecap="round" strokeDasharray="200 100" />
              </svg>
            )}
          </div>
        </div>
      </div>

      {/* Face-off */}
      <div
        className={`flex min-h-0 flex-1 items-center justify-center gap-[2.5vw] transition duration-500 ${
          over ? 'pointer-events-none opacity-35 blur-[2px]' : ''
        }`}
      >
        <div className="relative flex flex-col items-center gap-[1vh]" style={{ width: BOARD }}>
          <motion.div
            ref={humanRef}
            className="w-full rounded-xl shadow-[0_0_40px_6px_rgba(59,130,246,0.35)]"
            animate={feedbackA === 'wrong' ? shakeAnim : feedbackA === 'correct' ? flashAnim : {}}
            transition={{ duration: feedbackA === 'wrong' ? 0.45 : 0.6 }}
          >
            {puzzleA && <TugBoard puzzle={puzzleA} accent="blue" disabled={over} {...handlersA} />}
          </motion.div>
          <div className="flex items-center gap-2 text-[1.9vh] font-semibold text-white/60">
            <span className="text-blue-300">{toMove}</span>
            <AttemptDots used={state.boardA.wrongAttempts} />
          </div>
          <Toast show={skipToast.A} className="-top-1 bg-blue-500">
            {t('skipped')}
          </Toast>
        </div>

        <div className="flex flex-col items-center gap-[1vh] self-stretch py-[4vh]" aria-hidden="true">
          <div className="w-px flex-1 bg-white/10" />
          <span className="text-[2.6vh] font-black tracking-widest text-white/40">VS</span>
          <div className="w-px flex-1 bg-white/10" />
        </div>

        <div className="relative flex flex-col items-center gap-[1vh]" style={{ width: BOT_BOARD }}>
          <motion.div
            ref={zebraRef}
            className="w-full rounded-xl p-[0.6vh] shadow-[0_0_32px_4px_rgba(239,68,68,0.25)]"
            style={{ backgroundColor: 'rgba(127,29,29,0.35)' }}
            animate={feedbackB === 'wrong' ? shakeAnim : feedbackB === 'correct' ? flashAnim : {}}
            transition={{ duration: feedbackB === 'wrong' ? 0.45 : 0.6 }}
          >
            {botView.fen && (
              <BotBoard fen={botView.fen} lastMove={botView.lastMove} puzzleFen={puzzleB?.fen ?? botView.fen} />
            )}
          </motion.div>
          <div className="flex items-center gap-2 text-[1.9vh] font-semibold">
            <span
              aria-live="polite"
              className={`transition-opacity ${botView.thinking ? 'opacity-100' : 'opacity-0'}`}
              style={{ color: bot.color }}
            >
              {t('bot.zebraThinking')}
            </span>
            <AttemptDots used={state.boardB.wrongAttempts} />
          </div>
          <Toast show={skipToast.B} className="-top-1 bg-orange-500">
            {t('skipped')}
          </Toast>
          <Toast show={missed} className="top-[45%] bg-red-600" testId="tug-zebra-missed">
            {t('bot.zebraMissed')}
          </Toast>
        </div>
      </div>

      {/* "+1" fliers: solving board → knot */}
      {fliers.map((f) => (
        <motion.span
          key={f.id}
          aria-hidden="true"
          className={`pointer-events-none absolute z-30 -translate-x-1/2 -translate-y-1/2 text-[4.5vh] font-black drop-shadow-[0_2px_8px_rgba(0,0,0,0.8)] ${
            f.side === 'A' ? 'text-blue-400' : 'text-orange-400'
          }`}
          style={{ left: f.from.x, top: f.from.y }}
          initial={{ x: 0, y: 0, opacity: 0, scale: 0.6 }}
          animate={{ x: f.to.x - f.from.x, y: f.to.y - f.from.y, opacity: [0, 1, 1, 0], scale: [0.6, 1.2, 1, 0.8] }}
          transition={{ duration: 0.8, ease: 'easeInOut' }}
        >
          +1
        </motion.span>
      ))}

      {/* End card, anchored under the rope band */}
      <AnimatePresence>
        {over && (
          <motion.div
            data-testid="tug-arena-result"
            className="absolute left-1/2 top-[calc(18vh+3vh)] z-20 flex w-[min(92vw,720px)] -translate-x-1/2 flex-col items-center gap-5 rounded-3xl border border-white/10 bg-slate-900/90 px-6 py-8 shadow-2xl backdrop-blur"
            initial={{ opacity: 0, y: reduce ? 0 : -16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
          >
            <MatchResult
              state={state}
              isBot
              botName={botName}
              result={adaptive?.result}
              onRematch={onRematch}
              onTryFixed={adaptive ? onTryFixed : undefined}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Toast({
  show,
  className,
  testId,
  children,
}: {
  show: boolean;
  className: string;
  testId?: string;
  children: React.ReactNode;
}) {
  return (
    <AnimatePresence>
      {show && (
        <motion.div
          data-testid={testId}
          className={`absolute z-10 rounded-full px-4 py-1.5 text-sm font-bold shadow-lg ${className}`}
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
