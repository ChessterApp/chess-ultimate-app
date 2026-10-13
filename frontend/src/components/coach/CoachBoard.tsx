'use client';

import React from 'react';
import ChessgroundBoard from '@/components/chess/ChessgroundBoard';
import CoachBoardControls from './BoardControls';
import { Key } from 'chessground/types';

interface CoachBoardProps {
  fen: string;
  arrows: Array<{ from: Key; to: Key; brush: string }>;
  highlights: Key[];
  orientation: 'white' | 'black';
  boardSize?: number;
  /** False locks the pieces (a puzzle move waiting to be checked). */
  movable?: boolean;
  /** Laid over the board, which is its positioning box (verdict badge, toast). */
  overlay?: React.ReactNode;
  /** A colour wash after a checked answer; a new key replays it. */
  flash?: { result: 'correct' | 'wrong'; key: number } | null;
  onMove: (from: Key, to: Key, promotion?: 'q' | 'r' | 'b' | 'n') => void;
  onReset: () => void;
  onFirst: () => void;
  onPrev: () => void;
  onNext: () => void;
  onLast: () => void;
  onFlip: () => void;
}

export default function CoachBoard({
  fen,
  arrows,
  highlights,
  orientation,
  movable = true,
  overlay,
  flash,
  onMove,
  onReset,
  onFirst,
  onPrev,
  onNext,
  onLast,
  onFlip,
  boardSize = 520,
}: CoachBoardProps) {
  return (
    <div className="flex flex-col items-center">
      <div className="relative" style={{ width: boardSize, height: boardSize }}>
        <ChessgroundBoard
          fen={fen}
          orientation={orientation}
          onMove={onMove}
          arrows={arrows}
          highlightSquares={highlights}
          movable={movable}
          viewOnly={false}
          boardSize={boardSize}
        />
        {flash && (
          <div
            key={flash.key}
            aria-hidden
            data-testid="board-flash"
            className={`coach-board-flash pointer-events-none absolute inset-0 z-10 ring-4 ring-inset ${
              flash.result === 'correct'
                ? 'bg-(--coach-success-soft) ring-(--coach-success)'
                : 'bg-(--coach-danger-soft) ring-(--coach-danger)'
            }`}
          />
        )}
        {overlay}
      </div>
      <CoachBoardControls
        onReset={onReset}
        onFirst={onFirst}
        onPrev={onPrev}
        onNext={onNext}
        onLast={onLast}
        onFlip={onFlip}
        boardSize={boardSize}
      />
    </div>
  );
}
