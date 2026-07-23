'use client';

import React from 'react';
import type { Key } from 'chessground/types';
import { promotionLayout, type PromotionRole } from '@/lib/chess/promotion';

/** Fritz sprite letter + human label for each promotable piece. */
const PIECES: Record<PromotionRole, { sprite: string; label: string }> = {
  q: { sprite: 'Q', label: 'Queen' },
  r: { sprite: 'R', label: 'Rook' },
  b: { sprite: 'B', label: 'Bishop' },
  n: { sprite: 'N', label: 'Knight' },
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
            background: '#b0b0b0',
            boxShadow: '0 2px 10px rgba(0,0,0,0.55)',
          }}
        >
          <img
            src={`/static/pieces/Fritz/${color === 'white' ? 'w' : 'b'}${PIECES[role].sprite}.svg`}
            alt={PIECES[role].label}
            draggable={false}
            style={{
              width: square * 0.82,
              height: square * 0.82,
              pointerEvents: 'none',
            }}
          />
        </button>
      ))}
    </div>
  );
}
