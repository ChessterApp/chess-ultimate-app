'use client';

import React from 'react';

const PIECE_CODE: Record<string, string> = { p: 'P', n: 'N', b: 'B', r: 'R', q: 'Q', k: 'K' };

/** The 64 squares of a FEN's placement, rank 8 first: a piece letter or ''. */
export function fenSquares(fen: string): string[] {
  const rows = (fen.trim().split(/\s+/)[0] ?? '').split('/');
  const squares: string[] = [];
  for (const row of rows.slice(0, 8)) {
    for (const ch of row) {
      if (/\d/.test(ch)) squares.push(...Array<string>(Number(ch)).fill(''));
      else squares.push(ch);
    }
  }
  return squares.length === 64 ? squares : Array<string>(64).fill('');
}

interface MiniBoardProps {
  fen: string;
  size: number;
  /** Whose side is at the bottom; defaults to the side to move. */
  orientation?: 'white' | 'black';
  label: string;
}

/** A static thumbnail of a position (no chessground): the board's colours and pieces. */
export default function MiniBoard({ fen, size, orientation, label }: MiniBoardProps) {
  const side = orientation ?? (fen.trim().split(/\s+/)[1] === 'b' ? 'black' : 'white');
  const squares = fenSquares(fen);
  const ordered = side === 'black' ? [...squares].reverse() : squares;
  return (
    <div
      role="img"
      aria-label={label}
      className="grid shrink-0 grid-cols-8 overflow-hidden rounded-md"
      style={{ width: size, height: size }}
      data-testid="mini-board"
    >
      {ordered.map((piece, i) => {
        const index = side === 'black' ? 63 - i : i;
        const dark = (Math.floor(index / 8) + (index % 8)) % 2 === 1;
        const color = piece && piece === piece.toUpperCase() ? 'w' : 'b';
        return (
          <span key={i} className={dark ? 'bg-(--coach-board-dark)' : 'bg-(--coach-board-light)'}>
            {piece && (
              // eslint-disable-next-line @next/next/no-img-element -- tiny static sprites, no optimisation needed
              <img src={`/static/pieces/Fritz/${color}${PIECE_CODE[piece.toLowerCase()]}.svg`} alt="" className="h-full w-full" draggable={false} />
            )}
          </span>
        );
      })}
    </div>
  );
}
