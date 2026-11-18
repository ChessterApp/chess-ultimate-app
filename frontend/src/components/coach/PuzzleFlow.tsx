'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Chess, type Square } from 'chess.js';
import type { PuzzleState } from '@/types/coach';
import { useHaptic } from '@/hooks/useHaptic';
import { puzzleReplyDue, puzzleStudentColor, puzzleStudentMoves } from '@/hooks/useCoachBoard';
import { creditStepXp, useStepFlow, type StepComplete, type StepFlowControls } from '@/hooks/useStepFlow';
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
  /** Lock the board while a move waits for «Проверить», its result is shown or the opponent's reply is due. */
  boardLocked: boolean;
  flash: { result: 'correct' | 'wrong'; key: number } | null;
  /** The move played on the board (not checked yet). */
  move: (from: string, to: string, promotion?: 'q' | 'r' | 'b' | 'n') => void;
  undo: () => void;
  check: () => void;
  retry: () => void;
  /** «Дальше» on a right move: the opponent's reply first (at once if its pause has not run out), then the next step. */
  next: () => void;
  feedback: StepFeedback | null;
}

/**
 * Puzzle solving on StepFlow: a move is held until «Проверить», then checked
 * with the board hook's own solution check (useCoachBoard.validatePuzzleMove).
 * The steps are the student's moves only; the opponent's replies between them
 * are played by the board hook (useCoachBoard.playPuzzleReply, tester 18.11).
 */
export function usePuzzleStep(
  puzzle: PuzzleState | null,
  fen: string,
  validate: (from: string, to: string) => 'correct' | 'wrong' | 'solved',
  playReply?: () => void,
): PuzzleStepControls {
  const haptic = useHaptic();
  const [pending, setPending] = useState<PendingMove | null>(null);
  const [lastSan, setLastSan] = useState<string | null>(null);
  const [flash, setFlash] = useState<PuzzleStepControls['flash']>(null);

  // XP goes through the one credit path (creditStepXp); it credits nothing yet, so none is shown.
  const onStepComplete = useCallback((result: StepComplete) => void creditStepXp(result), []);
  // «Шаг N из M» counts the student's moves, not the opponent's replies (tester, 18.11).
  const total = puzzle ? puzzleStudentMoves(puzzle.solution) : 0;
  const flow = useStepFlow(total, onStepComplete);
  const replyDue = puzzleReplyDue(puzzle);

  // A new puzzle (the coach sent one, or a session was restored): start over.
  const puzzleKey = puzzle ? `${puzzle.fen}|${puzzle.solution.join(' ')}` : '';
  const { restart } = flow;
  useEffect(() => {
    restart(total);
    setPending(null);
    setLastSan(null);
    setFlash(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [puzzleKey, restart]);

  const move = useCallback(
    (from: string, to: string, promotion?: 'q' | 'r' | 'b' | 'n') => {
      const phase = flow.state.phase;
      if (phase !== 'idle' && phase !== 'moved') return;
      // The opponent's pieces are the board's to move (their reply), never the student's.
      if (!puzzle || replyDue) return;
      try {
        const chess = new Chess(fen);
        const piece = chess.get(from as Square);
        if (!piece || (piece.color === 'w' ? 'white' : 'black') !== puzzleStudentColor(puzzle.fen)) return;
        const m = chess.move({ from, to, promotion: promotion ?? 'q' });
        setPending({ from, to, san: m.san, fen: chess.fen() });
        flow.move();
      } catch {
        // Illegal: the board snaps back.
      }
    },
    [fen, flow, puzzle, replyDue],
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

  const next = useCallback(() => {
    if (replyDue) playReply?.();
    flow.next();
  }, [flow, replyDue, playReply]);

  const phase = flow.state.phase;
  return {
    flow,
    boardFen: pending?.fen ?? fen,
    boardLocked: phase !== 'idle' || replyDue,
    flash,
    move,
    undo,
    check,
    retry,
    next,
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
      // A warm-up puzzle says its place in the set (tester, 18.11: «номер задачи нигде не видно»).
      title={puzzle.place ? t('puzzlePlace', { n: puzzle.place.n, of: puzzle.place.of }) : t('puzzleTitle')}
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
      onNext={solved ? onNextPuzzle : controls.next}
      onFollowUp={onAsk}
      onClose={onExit}
    />
  );
}
