/**
 * SourceBadge — Small badge showing game source (TWIC/Lichess/Chess.com)
 */

'use client';

import React from 'react';
import { Chip } from '@mui/material';

export type GameSource = 'twic' | 'lichess' | 'chesscom' | 'pgn' | 'user' | 'internal';

interface SourceBadgeProps {
  source: GameSource | string;
}

const SOURCE_LABELS: Record<string, string> = {
  twic: 'Master Games',
  lichess: 'Lichess',
  chesscom: 'Chess.com',
  pgn: 'PGN',
  user: 'User',
  internal: 'Internal',
};

const SOURCE_COLORS: Record<string, { bg: string; color: string }> = {
  twic: { bg: '#1f2937', color: '#fff' },
  lichess: { bg: '#1b7f79', color: '#fff' },
  chesscom: { bg: '#81b64c', color: '#fff' },
  pgn: { bg: '#6b7280', color: '#fff' },
  user: { bg: '#3b82f6', color: '#fff' },
  internal: { bg: '#6b7280', color: '#fff' },
};

export default function SourceBadge({ source }: SourceBadgeProps) {
  const normalizedSource = source.toLowerCase();
  const label = SOURCE_LABELS[normalizedSource] || source;
  const colors = SOURCE_COLORS[normalizedSource] || { bg: '#6b7280', color: '#fff' };

  return (
    <Chip
      label={label}
      size="small"
      sx={{
        height: 18,
        fontSize: 10,
        fontWeight: 600,
        bgcolor: colors.bg,
        color: colors.color,
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
      }}
    />
  );
}
