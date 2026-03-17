'use client';

import React from 'react';
import { Box, Typography, Chip } from '@mui/material';
import type { MoveCandidate } from '@/hooks/useOpeningRepertoire';

interface PositionSummaryProps {
  ecoCode: string | null;
  openingName: string | null;
  totalGames: number;
  moves: MoveCandidate[];
}

export default function PositionSummary({ ecoCode, openingName, totalGames, moves }: PositionSummaryProps) {
  // Aggregate W/D/L across all moves
  const totals = moves.reduce(
    (acc, m) => ({
      white: acc.white + m.white_wins,
      draws: acc.draws + m.draws,
      black: acc.black + m.black_wins,
    }),
    { white: 0, draws: 0, black: 0 }
  );

  const total = totals.white + totals.draws + totals.black;
  const wPct = total > 0 ? (totals.white / total) * 100 : 0;
  const dPct = total > 0 ? (totals.draws / total) * 100 : 0;
  const bPct = total > 0 ? (totals.black / total) * 100 : 0;

  if (!ecoCode && !openingName && totalGames === 0) return null;

  return (
    <Box sx={{ px: 1.5, py: 1 }}>
      {/* ECO + Opening name */}
      {(ecoCode || openingName) && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.75, flexWrap: 'wrap' }}>
          {ecoCode && (
            <Chip
              label={ecoCode}
              size="small"
              sx={{
                bgcolor: '#1f2937',
                color: 'primary.contrastText',
                fontWeight: 600,
                fontSize: 11,
                height: 20,
              }}
            />
          )}
          {openingName && (
            <Typography sx={{ color: 'var(--text-secondary)', fontSize: 12, fontWeight: 500 }}>
              {openingName}
            </Typography>
          )}
        </Box>
      )}

      {/* Total games + aggregate W/D/L bar */}
      {totalGames > 0 && (
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
            <Typography sx={{ color: 'var(--text-tertiary)', fontSize: 11 }}>
              {totalGames.toLocaleString()} games
            </Typography>
          </Box>

          {/* Aggregate bar */}
          <Box
            sx={{
              display: 'flex',
              width: '100%',
              height: 14,
              borderRadius: '3px',
              overflow: 'hidden',
              mb: 0.5,
            }}
          >
            <Box sx={{ width: `${wPct}%`, bgcolor: '#f0f0f0', minWidth: wPct > 0 ? 2 : 0 }} />
            <Box sx={{ width: `${dPct}%`, bgcolor: '#888', minWidth: dPct > 0 ? 2 : 0 }} />
            <Box sx={{ width: `${bPct}%`, bgcolor: '#333', minWidth: bPct > 0 ? 2 : 0 }} />
          </Box>

          {/* Percentage labels */}
          <Box sx={{ display: 'flex', gap: 1.5 }}>
            <Typography sx={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
              <Box component="span" sx={{ display: 'inline-block', width: 8, height: 8, bgcolor: '#f0f0f0', borderRadius: '1px', mr: 0.3, verticalAlign: 'middle' }} />
              {wPct.toFixed(1)}%
            </Typography>
            <Typography sx={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
              <Box component="span" sx={{ display: 'inline-block', width: 8, height: 8, bgcolor: '#888', borderRadius: '1px', mr: 0.3, verticalAlign: 'middle' }} />
              {dPct.toFixed(1)}%
            </Typography>
            <Typography sx={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
              <Box component="span" sx={{ display: 'inline-block', width: 8, height: 8, bgcolor: '#333', borderRadius: '1px', mr: 0.3, verticalAlign: 'middle' }} />
              {bPct.toFixed(1)}%
            </Typography>
          </Box>
        </Box>
      )}
    </Box>
  );
}
