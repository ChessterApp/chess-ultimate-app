'use client';

/**
 * WatchtowerBoard — a compact, dependency-free interactive board for the
 * companion Watchtower nodes and due reviews. Renders a FEN as an 8×8 grid of
 * Unicode glyphs (white at the bottom) and collects a submission the server
 * validates — the client NEVER judges (plan A7):
 *   • validator 'squares' → tap pieces/squares to build a set  → { squares: [...] }
 *   • validator 'move'    → tap a from-square then a to-square  → { uci }
 */
import { useMemo, useState } from 'react';
import type { Submission } from '@/lib/companion/assessment';

const GLYPH: Record<string, string> = {
  K: '♔', Q: '♕', R: '♖', B: '♗', N: '♘', P: '♙',
  k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟',
};
const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];

/** Expand a FEN piece-placement field into 64 cells (rank 8 → rank 1). */
function parseBoard(fen: string): (string | null)[] {
  const placement = (fen ?? '').trim().split(/\s+/)[0] ?? '';
  const cells: (string | null)[] = [];
  for (const rank of placement.split('/')) {
    for (const ch of rank) {
      if (/\d/.test(ch)) for (let i = 0; i < Number(ch); i++) cells.push(null);
      else cells.push(ch);
    }
  }
  while (cells.length < 64) cells.push(null);
  return cells.slice(0, 64);
}

function squareName(row: number, col: number): string {
  return `${FILES[col]}${8 - row}`;
}

interface Props {
  fen: string;
  validator: string;
  onSubmit: (submission: Submission) => void;
  disabled?: boolean;
  submitLabel: string;
  clearLabel: string;
}

export default function WatchtowerBoard({
  fen,
  validator,
  onSubmit,
  disabled,
  submitLabel,
  clearLabel,
}: Props) {
  const cells = useMemo(() => parseBoard(fen), [fen]);
  const isSquares = validator === 'squares';
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [from, setFrom] = useState<string | null>(null);
  const [to, setTo] = useState<string | null>(null);

  const highlighted = (sq: string) =>
    isSquares ? selected.has(sq) : sq === from || sq === to;

  const onCell = (sq: string, hasPiece: boolean) => {
    if (disabled) return;
    if (isSquares) {
      setSelected((prev) => {
        const next = new Set(prev);
        if (next.has(sq)) next.delete(sq);
        else next.add(sq);
        return next;
      });
      return;
    }
    // move mode: pick a from-square (must hold a piece), then a to-square.
    if (!from) {
      if (hasPiece) setFrom(sq);
      return;
    }
    if (sq === from) {
      setFrom(null);
      setTo(null);
      return;
    }
    setTo(sq);
  };

  const reset = () => {
    setSelected(new Set());
    setFrom(null);
    setTo(null);
  };

  const canSubmit = isSquares ? selected.size > 0 : !!(from && to);

  const submit = () => {
    if (!canSubmit) return;
    onSubmit(isSquares ? { squares: [...selected] } : { uci: `${from}${to}` });
  };

  return (
    <div>
      <div className="mx-auto grid w-full max-w-xs grid-cols-8 overflow-hidden rounded-lg border border-gray-300 dark:border-[#2a2a2a]">
        {cells.map((piece, i) => {
          const row = Math.floor(i / 8);
          const col = i % 8;
          const sq = squareName(row, col);
          const light = (row + col) % 2 === 0;
          return (
            <button
              key={sq}
              type="button"
              aria-label={sq}
              onClick={() => onCell(sq, !!piece)}
              disabled={disabled}
              className={`flex aspect-square items-center justify-center text-2xl leading-none transition-colors ${
                light ? 'bg-[#eff2f7] dark:bg-[#2b2b33]' : 'bg-[#b7c0d0] dark:bg-[#3a3a45]'
              } ${highlighted(sq) ? 'ring-2 ring-inset ring-green-500' : ''}`}
            >
              <span className={piece && piece === piece.toLowerCase() ? 'text-gray-900' : 'text-white'}>
                {piece ? GLYPH[piece] ?? '' : ''}
              </span>
            </button>
          );
        })}
      </div>
      <div className="mt-3 flex justify-center gap-2">
        <button
          type="button"
          onClick={reset}
          disabled={disabled}
          className="rounded-full border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-50 dark:border-[#2a2a2a] dark:text-gray-300 dark:hover:bg-[#1f1f1f]"
        >
          {clearLabel}
        </button>
        <button
          type="button"
          onClick={submit}
          disabled={disabled || !canSubmit}
          className="rounded-full bg-green-600 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-green-700 disabled:opacity-50"
        >
          {submitLabel}
        </button>
      </div>
    </div>
  );
}
