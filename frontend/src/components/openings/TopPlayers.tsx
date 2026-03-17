'use client';

import React, { useState } from 'react';
import { Box, Typography, CircularProgress } from '@mui/material';
import { ExpandMore, ExpandLess } from '@mui/icons-material';
import type { TopPlayer } from '@/hooks/useOpeningRepertoire';

interface TopPlayersProps {
  players: TopPlayer[];
  loading: boolean;
}

export default function TopPlayers({ players, loading }: TopPlayersProps) {
  const [expanded, setExpanded] = useState(false);
  const INITIAL_SHOW = 5;

  if (loading) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 1, px: 1.5 }}>
        <CircularProgress size={12} sx={{ color: '#14b8a6' }} />
        <Typography variant="caption" sx={{ color: 'var(--text-tertiary)', fontSize: 10 }}>
          Loading players...
        </Typography>
      </Box>
    );
  }

  if (players.length === 0) return null;

  const visiblePlayers = expanded ? players : players.slice(0, INITIAL_SHOW);

  return (
    <Box sx={{ px: 1.5, py: 0.75 }}>
      <Typography
        sx={{
          fontSize: 10,
          fontWeight: 600,
          color: 'var(--text-tertiary)',
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
          mb: 0.5,
        }}
      >
        Top Players
      </Typography>

      {visiblePlayers.map((p, idx) => (
        <Box
          key={p.name}
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 0.5,
            py: 0.2,
          }}
        >
          <Typography sx={{ fontSize: 11, color: 'var(--text-tertiary)', minWidth: 14 }}>
            {idx + 1}.
          </Typography>
          {p.title && (
            <Typography
              component="span"
              sx={{
                fontSize: 10,
                fontWeight: 700,
                color: p.title === 'GM' ? '#d4a017' : 'var(--text-secondary)',
              }}
            >
              {p.title}
            </Typography>
          )}
          <Typography sx={{ fontSize: 11, color: 'var(--text-primary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {p.name}
          </Typography>
          <Typography sx={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'monospace' }}>
            ({p.elo})
          </Typography>
          <Typography sx={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
            {p.games}g
          </Typography>
        </Box>
      ))}

      {players.length > INITIAL_SHOW && (
        <Box
          onClick={() => setExpanded(!expanded)}
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 0.3,
            cursor: 'pointer',
            mt: 0.3,
            '&:hover': { color: '#14b8a6' },
          }}
        >
          {expanded ? (
            <ExpandLess sx={{ fontSize: 14, color: 'var(--text-tertiary)' }} />
          ) : (
            <ExpandMore sx={{ fontSize: 14, color: 'var(--text-tertiary)' }} />
          )}
          <Typography sx={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
            {expanded ? 'Show less' : `Show ${players.length - INITIAL_SHOW} more`}
          </Typography>
        </Box>
      )}
    </Box>
  );
}
