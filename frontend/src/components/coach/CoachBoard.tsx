'use client';

import React, { useCallback, useRef, useState } from 'react';
import ChessgroundBoard from '@/components/chess/ChessgroundBoard';
import CoachBoardControls from './BoardControls';
import { Key } from 'chessground/types';

interface CoachBoardProps {
  fen: string;
  arrows: Array<{ from: Key; to: Key; brush: string }>;
  highlights: Key[];
  orientation: 'white' | 'black';
  /**
   * Board px with the control bar under it (desktop). Without it the board is
   * fluid: the largest square its box allows (the box is sized by CSS), and no
   * control bar — the mobile shell's move strip stands in for it.
   */
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
  /** The move to highlight (from, to). */
  lastMove?: [Key, Key] | null;
  /** The board's own move buttons; off when the game strip shows its own (desktop game, audit 26.10). */
  controls?: boolean;
  /** Piece animation in ms (the coach page's setting); 0 = instant. */
  animationDuration?: number;
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
  animationDuration,
  lastMove = null,
  controls = true,
  onReset,
  onFirst,
  onPrev,
  onNext,
  onLast,
  onFlip,
  boardSize,
}: CoachBoardProps) {
  const [measureBox, fluidSize] = useBoxSquare();
  const board = (size: number) => (
    <div className="relative" style={{ width: size, height: size }}>
      <ChessgroundBoard
        fen={fen}
        orientation={orientation}
        onMove={onMove}
        arrows={arrows}
        highlightSquares={highlights}
        movable={movable}
        viewOnly={false}
        boardSize={size}
        animationDuration={animationDuration}
        lastMove={lastMove}
      />
      <BoardFlash flash={flash} />
      {overlay}
    </div>
  );
  if (boardSize === undefined) {
    return (
      <div ref={measureBox} className="flex h-full w-full items-center justify-center" data-testid="coach-board-fluid">
        {fluidSize > 0 && board(fluidSize)}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center">
      {board(boardSize)}
      {controls && <CoachBoardControls
        onReset={onReset}
        onFirst={onFirst}
        onPrev={onPrev}
        onNext={onNext}
        onLast={onLast}
        onFlip={onFlip}
        boardSize={boardSize}
      />}
    </div>
  );
}

/** A colour wash after a checked answer; a new key replays it. */
function BoardFlash({ flash }: { flash: CoachBoardProps['flash'] }) {
  if (!flash) return null;
  return (
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
  );
}

/** The largest square (px, a multiple of 8 for crisp squares) the observed box holds. */
function useBoxSquare(): [(el: HTMLDivElement | null) => void, number] {
  const [size, setSize] = useState(0);
  const observer = useRef<ResizeObserver | null>(null);
  const measureBox = useCallback((el: HTMLDivElement | null) => {
    observer.current?.disconnect();
    observer.current = null;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const measure = () => {
      const side = Math.floor(Math.min(el.clientWidth, el.clientHeight) / 8) * 8;
      if (side > 0) setSize(side);
    };
    measure();
    observer.current = new ResizeObserver(measure);
    observer.current.observe(el);
  }, []);
  return [measureBox, size];
}
