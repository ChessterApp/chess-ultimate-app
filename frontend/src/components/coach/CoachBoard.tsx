'use client';

import React, { useState, useCallback } from 'react';
import ChessgroundBoard from '@/components/chess/ChessgroundBoard';
import CoachBoardControls from './BoardControls';
import PuzzleOverlay from './PuzzleOverlay';
import type { CoachBoardState, PuzzleState } from '@/types/coach';
import { Key } from 'chessground/types';

interface CoachBoardProps {
  fen: string;
  arrows: Array<{ from: Key; to: Key; brush: string }>;
  highlights: Key[];
  orientation: 'white' | 'black';
  puzzleMode: boolean;
  puzzleState: PuzzleState | null;
  moveIndex: number;
  pgnLength: number;
  onMove: (from: Key, to: Key) => void;
  onFirst: () => void;
  onPrev: () => void;
  onNext: () => void;
  onLast: () => void;
  onFlip: () => void;
  onPuzzleMove: (from: string, to: string) => 'correct' | 'wrong' | 'solved';
}

export default function CoachBoard({
  fen,
  arrows,
  highlights,
  orientation,
  puzzleMode,
  puzzleState,
  moveIndex,
  pgnLength,
  onMove,
  onFirst,
  onPrev,
  onNext,
  onLast,
  onFlip,
  onPuzzleMove,
}: CoachBoardProps) {
  const [puzzleResult, setPuzzleResult] = useState<'correct' | 'wrong' | 'solved' | null>(null);

  const handleMove = useCallback(
    (from: Key, to: Key) => {
      if (puzzleMode && puzzleState && !puzzleState.solved) {
        const result = onPuzzleMove(from as string, to as string);
        setPuzzleResult(result);
      } else {
        onMove(from, to);
      }
    },
    [puzzleMode, puzzleState, onPuzzleMove, onMove]
  );

  const handleDismissPuzzle = useCallback(() => {
    setPuzzleResult(null);
  }, []);

  return (
    <div className="flex flex-col items-center">
      <div className="relative">
        <ChessgroundBoard
          fen={fen}
          orientation={orientation}
          onMove={handleMove}
          arrows={arrows}
          highlightSquares={highlights}
          movable={true}
          viewOnly={false}
          boardSize={520}
        />
        <PuzzleOverlay result={puzzleResult} onDismiss={handleDismissPuzzle} />
      </div>
      <CoachBoardControls
        onFirst={onFirst}
        onPrev={onPrev}
        onNext={onNext}
        onLast={onLast}
        onFlip={onFlip}
        canGoPrev={pgnLength > 0 && moveIndex > 0}
        canGoNext={pgnLength > 0 && moveIndex < pgnLength - 1}
      />
    </div>
  );
}
