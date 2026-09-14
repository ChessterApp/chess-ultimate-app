/**
 * MatchScreen — the live 16:9 smartboard layout: top score bar, rope zone,
 * two boards with per-board feedback (green flash / red shake / skip toast),
 * and the win overlay with a Rematch button.
 */

'use client';

import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import TugBoard from './TugBoard';
import RopeScene from './RopeScene';
import { TUG_STRINGS as S } from '@/lib/tug-of-war/strings';
import { currentPuzzle, MAX_WRONG_ATTEMPTS } from '@/lib/tug-of-war/gameReducer';
import type { GameState, GameAction } from '@/lib/tug-of-war/gameReducer';
import type { TeamSide } from '@/lib/tug-of-war/types';

type Feedback = 'idle' | 'correct' | 'wrong';

interface MatchScreenProps {
  state: GameState;
  dispatch: (action: GameAction) => void;
}

function AttemptDots({ used }: { used: number }) {
  return (
    <div className="flex items-center gap-1" aria-label={`${used} of ${MAX_WRONG_ATTEMPTS} wrong`}>
      {Array.from({ length: MAX_WRONG_ATTEMPTS }).map((_, i) => (
        <span
          key={i}
          className={`h-2.5 w-2.5 rounded-full ${i < used ? 'bg-red-500' : 'bg-white/25'}`}
        />
      ))}
    </div>
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

export default function MatchScreen({ state, dispatch }: MatchScreenProps) {
  const [feedbackA, setFeedbackA] = useState<Feedback>('idle');
  const [feedbackB, setFeedbackB] = useState<Feedback>('idle');
  const [skipToast, setSkipToast] = useState<{ A: boolean; B: boolean }>({ A: false, B: false });

  const over = state.phase === 'over';
  const puzzleA = currentPuzzle(state.boardA);
  const puzzleB = currentPuzzle(state.boardB);

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
      dispatch({ type: 'SOLVE', team });
      setTimeout(() => setFeedback('idle'), 650);
    },
    onWrong: () => {
      setFeedback('wrong');
      dispatch({ type: 'WRONG', team });
      setTimeout(() => setFeedback('idle'), 550);
    },
  });

  const handlersA = makeHandlers('A', setFeedbackA);
  const handlersB = makeHandlers('B', setFeedbackB);

  const winnerName = state.winner === 'A' ? state.teamAName : state.teamBName;

  return (
    <div className="relative mx-auto flex min-h-screen max-w-[1600px] flex-col gap-4 px-4 py-4 text-white sm:px-6">
      {/* Top bar */}
      <div className="flex items-center justify-between rounded-2xl border border-white/10 bg-white/5 px-5 py-3">
        <TeamHeader name={state.teamAName} score={state.boardA.solved} accent="blue" align="left" />
        <div className="text-center">
          <div className="text-xs font-bold uppercase tracking-widest text-white/40">Rope</div>
          <div className="text-2xl font-black tabular-nums">
            {state.rope > 0 ? `+${state.rope}` : state.rope}
          </div>
        </div>
        <TeamHeader name={state.teamBName} score={state.boardB.solved} accent="orange" align="right" />
      </div>

      {/* Rope zone */}
      <RopeScene rope={state.rope} winner={state.winner} />

      {/* Boards */}
      <div className="grid flex-1 grid-cols-1 items-start gap-4 md:grid-cols-2">
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

      {/* Win overlay */}
      <AnimatePresence>
        {over && (
          <motion.div
            className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-6 bg-slate-950/80 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.h2
              className={`text-center text-5xl font-black tracking-tight sm:text-6xl ${
                state.winner === 'A' ? 'text-blue-400' : 'text-orange-400'
              }`}
              initial={{ scale: 0.6, y: 20 }}
              animate={{ scale: 1, y: 0 }}
              transition={{ type: 'spring', stiffness: 200, damping: 12 }}
            >
              {S.wins(winnerName)}
            </motion.h2>
            <button
              onClick={() => dispatch({ type: 'REMATCH' })}
              className="rounded-xl bg-white px-8 py-4 text-xl font-black text-slate-900 shadow-lg transition hover:brightness-95 active:scale-95"
            >
              {S.rematch}
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
      <div className="text-3xl font-black tabular-nums sm:text-4xl">{score}</div>
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
  return (
    <div className="relative flex flex-col items-center gap-2">
      <motion.div
        className="w-full max-w-[560px] rounded-xl"
        animate={
          feedback === 'wrong' ? shakeAnim : feedback === 'correct' ? flashAnim : {}
        }
        transition={{ duration: feedback === 'wrong' ? 0.45 : 0.6 }}
      >
        {children}
      </motion.div>
      <AttemptDots used={used} />
      <AnimatePresence>
        {skip && (
          <motion.div
            className={`absolute -top-3 rounded-full px-4 py-1.5 text-sm font-bold shadow-lg ${
              accent === 'blue' ? 'bg-blue-500' : 'bg-orange-500'
            }`}
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
          >
            {S.skipped}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
