/**
 * EmptyState — Contextual empty state component for explorer tabs
 */

'use client';

import React from 'react';
import { Box, Typography } from '@mui/material';
import { Search, Info, SportsEsports } from '@mui/icons-material';

export type EmptyStateType = 'no-games' | 'no-search' | 'no-results' | 'position-search-unavailable';

interface EmptyStateProps {
  type: EmptyStateType;
  message?: string;
  hint?: string;
}

const EMPTY_STATE_CONFIG: Record<EmptyStateType, { icon: React.ReactNode; defaultMessage: string; defaultHint?: string }> = {
  'no-games': {
    icon: <SportsEsports sx={{ fontSize: 40, color: 'text.secondary', opacity: 0.4 }} />,
    defaultMessage: 'No games found for this position',
    defaultHint: 'Try exploring a different position or adjusting your filters',
  },
  'no-search': {
    icon: <Search sx={{ fontSize: 40, color: 'text.secondary', opacity: 0.4 }} />,
    defaultMessage: 'Enter search criteria to see results',
    defaultHint: 'Search by player name to explore their games',
  },
  'no-results': {
    icon: <Search sx={{ fontSize: 40, color: 'text.secondary', opacity: 0.4 }} />,
    defaultMessage: 'No games match your filters',
    defaultHint: 'Try adjusting your search filters or time control settings',
  },
  'position-search-unavailable': {
    icon: <Info sx={{ fontSize: 40, color: 'text.secondary', opacity: 0.4 }} />,
    defaultMessage: 'Position search not available',
    defaultHint: 'Use player search to explore games from this source',
  },
};

export default function EmptyState({ type, message, hint }: EmptyStateProps) {
  const config = EMPTY_STATE_CONFIG[type];

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        py: 4,
        px: 2,
        textAlign: 'center',
      }}
    >
      {config.icon}
      <Typography
        variant="body2"
        sx={{
          color: 'text.secondary',
          fontSize: 13,
          fontWeight: 500,
          mt: 1.5,
          mb: 0.5,
        }}
      >
        {message || config.defaultMessage}
      </Typography>
      {(hint || config.defaultHint) && (
        <Typography
          variant="caption"
          sx={{
            color: 'text.secondary',
            fontSize: 11,
            opacity: 0.7,
            maxWidth: 300,
          }}
        >
          {hint || config.defaultHint}
        </Typography>
      )}
    </Box>
  );
}
