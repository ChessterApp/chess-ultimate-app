'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Chess } from 'chess.js';
import type { PuzzleState } from '@/types/coach';
import { useHaptic } from '@/hooks/useHaptic';
import { useStepFlow, type StepComplete, type StepFlowControls } from '@/hooks/useStepFlow';
import StepFlow, { type StepFeedback } from './StepFlow';

interface PendingMove {
  from: string;
  to: string;
  san: string;
  /** The position after the move: shown until it is checked. */
  fen: string;
}

export interface PuzzleStepControls {
  flow: StepFlowControls;
  /** The position to show: the puzzle's, or the not-yet-checked move. */
  boardFen: string;
  /** Lock the board while a move waits for «Проверить» or its result is shown. */
  boardLocked: boolean;
  flash: { result: 'correct' | 'wrong'; key: number } | null;
  /** The move played on the board (not checked yet). */
  move: (from: string, to: string, promotion?: 'q' | 'r' | 'b' | 'n') => void;
  undo: () => void;
  check: () => void;
  retry: () => void;
  feedback: StepFeedback | null;
}

/**
 * Puzzle solving on StepFlow: a move is held until «Проверить», then checked
 * with the board hook's own solution check (useCoachBoard.validatePuzzleMove).
 */
export function usePuzzleStep(
  puzzle: PuzzleState | null,
  fen: string,
  validate: (from: string, to: string) => 'correct' | 'wrong' | 'solved',
): PuzzleStepControls {
  const haptic = useHaptic();
  const [pending, setPending] = useState<PendingMove | null>(null);
  const [lastSan, setLastSan] = useState<string | null>(null);
  const [flash, setFlash] = useState<PuzzleStepControls['flash']>(null);

  // TODO(coach-xp): there is no client→server path for crediting puzzle XP yet
  // (XP comes from the server-side sync jobs and companion assignments only).
  // Wire the gamification call here once one exists; until then XP is not shown.
  const onStepComplete = useCallback((_result: StepComplete) => {}, []);
  const flow = useStepFlow(puzzle?.solution.length ?? 0, onStepComplete);

  // A new puzzle (the coach sent one, or a session was restored): start over.
  const puzzleKey = puzzle ? `${puzzle.fen}|${puzzle.solution.join(' ')}` : '';
  const { restart } = flow;
  useEffect(() => {
    restart(puzzle?.solution.length ?? 0);
    setPending(null);
    setLastSan(null);
    setFlash(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [puzzleKey, restart]);

  const move = useCallback(
    (from: string, to: string, promotion?: 'q' | 'r' | 'b' | 'n') => {
      const phase = flow.state.phase;
      if (phase !== 'idle' && phase !== 'moved') return;
      try {
        const chess = new Chess(fen);
        const m = chess.move({ from, to, promotion: promotion ?? 'q' });
        setPending({ from, to, san: m.san, fen: chess.fen() });
        flow.move();
      } catch {
        // Illegal: the board snaps back.
      }
    },
    [fen, flow],
  );

  const check = useCallback(() => {
    if (!pending) return;
    void flow.check(() => {
      const result = validate(pending.from, pending.to);
      const correct = result !== 'wrong';
      setLastSan(pending.san);
      setPending(null);
      setFlash({ result: correct ? 'correct' : 'wrong', key: Date.now() });
      if (correct) haptic.onPuzzleCorrect();
      else haptic.onPuzzleWrong();
      return correct;
    });
  }, [pending, flow, validate, haptic]);

  const undo = useCallback(() => {
    setPending(null);
    flow.undo();
  }, [flow]);

  const retry = useCallback(() => {
    setLastSan(null);
    flow.retry();
  }, [flow]);

  const phase = flow.state.phase;
  return {
    flow,
    boardFen: pending?.fen ?? fen,
    boardLocked: phase !== 'idle',
    flash,
    move,
    undo,
    check,
    retry,
    feedback: phase === 'correct' || phase === 'wrong' ? { san: lastSan ?? undefined } : null,
  };
}

interface PuzzleFlowProps {
  controls: PuzzleStepControls;
  puzzle: PuzzleState;
  /** Ask the coach in the chat (hint, «Почему …?»). */
  onAsk: (message: string) => void;
  /** The puzzle is solved and «Дальше» was pressed. */
  onNextPuzzle: () => void;
  onExit: () => void;
}

/** The puzzle panel: StepFlow with the puzzle's question, hint, check and next. */
export default function PuzzleFlow({ controls, puzzle, onAsk, onNextPuzzle, onExit }: PuzzleFlowProps) {
  const t = useTranslations('coach');
  const { flow, feedback } = controls;
  const whiteToMove = puzzle.fen.split(' ')[1] !== 'b';
  const prompt =
    flow.state.index === 0 ? (whiteToMove ? t('puzzleWhiteToWin') : t('puzzleBlackToWin')) : t('puzzleKeepGoing');
  const solved = flow.state.phase === 'correct' && flow.state.index + 1 >= flow.state.total;
  const san = feedback?.san;

  return (
    <StepFlow
      title={t('puzzleTitle')}
      state={flow.state}
      prompt={prompt}
      feedback={
        feedback && flow.state.phase === 'correct' && san
          ? { ...feedback, followUp: { label: t('puzzleWhyChip', { move: san }), message: t('puzzleWhyMessage', { move: san }) } }
          : feedback
      }
      onHint={() => onAsk(t('puzzleHintMessage'))}
      onUndo={controls.undo}
      onCheck={controls.check}
      onRetry={controls.retry}
      onNext={solved ? onNextPuzzle : flow.next}
      onFollowUp={onAsk}
      onClose={onExit}
    />
  );
}
