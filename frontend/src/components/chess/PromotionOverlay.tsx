'use client';

import React from 'react';
import type { Key } from 'chessground/types';
import { promotionLayout, type PromotionRole } from '@/lib/chess/promotion';

/** Filled glyph + human label for each promotable piece. */
const PIECES: Record<PromotionRole, { glyph: string; label: string }> = {
  q: { glyph: '♛', label: 'Queen' },
  r: { glyph: '♜', label: 'Rook' },
  b: { glyph: '♝', label: 'Bishop' },
  n: { glyph: '♞', label: 'Knight' },
};

interface PromotionOverlayProps {
  /** Target square of the held pawn move (e.g. 'e8'). */
  to: Key;
  /** Colour of the promoting pawn. */
  color: 'white' | 'black';
  orientation: 'white' | 'black';
  boardSize: number;
  onSelect: (role: PromotionRole) => void;
  onCancel: () => void;
}

/**
 * Lichess-style promotion picker: a dimmed board with a column of Q/R/B/N
 * choices dropping from the target square. Tapping a piece promotes; tapping
 * anywhere else cancels and the pawn snaps back to its origin.
 */
export default function PromotionOverlay({
  to,
  color,
  orientation,
  boardSize,
  onSelect,
  onCancel,
}: PromotionOverlayProps) {
  const square = boardSize / 8;
  const cells = promotionLayout(to, orientation);

  return (
    <div
      data-testid="promotion-overlay"
      onClick={onCancel}
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 30,
        background: 'rgba(0,0,0,0.5)',
        cursor: 'pointer',
      }}
    >
      {cells.map(({ role, col, row }) => (
        <button
          key={role}
          type="button"
          data-testid={`promotion-${role}`}
          aria-label={`Promote to ${PIECES[role].label}`}
          onClick={(e) => {
            e.stopPropagation();
            onSelect(role);
          }}
          style={{
            position: 'absolute',
            left: col * square,
            top: row * square,
            width: square,
            height: square,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 0,
            border: 'none',
            borderRadius: '50%',
            cursor: 'pointer',
            fontSize: square * 0.72,
            lineHeight: 1,
            background: color === 'white' ? '#f7f7f7' : '#2b2b2b',
            color: color === 'white' ? '#111' : '#f7f7f7',
            boxShadow: '0 2px 10px rgba(0,0,0,0.55)',
          }}
        >
          {PIECES[role].glyph}
        </button>
      ))}
    </div>
  );
}
