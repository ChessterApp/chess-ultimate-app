/**
 * GameTable — Shared compact table layout for displaying game lists
 * Used by NodeDetailsPanel (TWIC), LichessExplorerTab, ChessComExplorerTab
 * Columns: Year | White | Elo | Black | Elo | Result | ECO
 */

'use client';

import React from 'react';
import {
  Box,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  Typography,
} from '@mui/material';
import type { GameSearchResult } from '@/hooks/useOpeningRepertoire';

interface GameTableProps {
  games: GameSearchResult[];
  onOpenGame?: (game: GameSearchResult) => void;
  loading?: boolean;
}

export default function GameTable({ games, onOpenGame, loading }: GameTableProps) {
  if (games.length === 0) return null;

  return (
    <Box sx={{ overflowX: 'auto', opacity: loading ? 0.5 : 1, transition: 'opacity 0.15s ease' }}>
      <Table size="small" sx={{ minWidth: 420 }}>
        <TableHead>
          <TableRow>
            <TableCell sx={thSx}>Year</TableCell>
            <TableCell sx={thSx}>White</TableCell>
            <TableCell sx={thSx}>Elo</TableCell>
            <TableCell sx={thSx}>Black</TableCell>
            <TableCell sx={thSx}>Elo</TableCell>
            <TableCell sx={thSx}>Result</TableCell>
            <TableCell sx={thSx}>ECO</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {games.map((game, idx) => (
            <TableRow
              key={game.id ?? idx}
              onClick={() => onOpenGame?.(game)}
              sx={{
                cursor: onOpenGame ? 'pointer' : 'default',
                '&:hover': { bgcolor: 'rgba(255,255,255,0.06)' },
              }}
            >
              <TableCell sx={tdSx}>
                {extractYear(game) || '—'}
              </TableCell>
              <TableCell sx={{ ...tdSx, maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {game.white_name || game.white || '?'}
              </TableCell>
              <TableCell sx={{ ...tdSx, color: 'text.secondary' }}>
                {game.white_elo ?? '—'}
              </TableCell>
              <TableCell sx={{ ...tdSx, maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {game.black_name || game.black || '?'}
              </TableCell>
              <TableCell sx={{ ...tdSx, color: 'text.secondary' }}>
                {game.black_elo ?? '—'}
              </TableCell>
              <TableCell sx={{
                ...tdSx,
                fontWeight: 600,
                color: game.result === '1-0' ? '#4ade80' : game.result === '0-1' ? '#f87171' : '#9ca3af',
              }}>
                {game.result || '?'}
              </TableCell>
              <TableCell sx={{ ...tdSx, color: 'text.secondary' }}>
                {game.eco || ''}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}

function extractYear(game: GameSearchResult): string {
  if (game.year) return String(game.year).substring(0, 4);
  if (game.date) return game.date.substring(0, 4);
  return '';
}

const thSx = {
  fontSize: 10,
  fontWeight: 700,
  color: 'text.secondary',
  textTransform: 'uppercase' as const,
  letterSpacing: 0.5,
  py: 0.75,
  px: 0.75,
  borderBottom: '1px solid rgba(255,255,255,0.08)',
  whiteSpace: 'nowrap' as const,
};

const tdSx = {
  fontSize: 12,
  color: 'text.primary',
  py: 0.5,
  px: 0.75,
  borderBottom: '1px solid rgba(255,255,255,0.04)',
  whiteSpace: 'nowrap' as const,
};
