'use client';

import React, { useState, useMemo } from 'react';
import { Box, Typography, LinearProgress, Select, MenuItem } from '@mui/material';
import type { MoveCandidate } from '@/hooks/useOpeningRepertoire';

export type MoveTreeSource = 'twic' | 'lichess-masters' | 'lichess-players';

interface MoveTreeProps {
  moves: MoveCandidate[];
  totalGames: number;
  loading: boolean;
  onMoveClick: (move: MoveCandidate) => void;
  fen?: string; // Current position FEN — used for move numbering
  source?: MoveTreeSource;
  onSourceChange?: (source: MoveTreeSource) => void;
}

type SortField = 'count' | 'percentage' | 'avg_elo' | 'avg_year' | 'san';
type SortDir = 'asc' | 'desc';

const DEFAULT_VISIBLE = 5;

export default function MoveTree({ moves, totalGames, loading, onMoveClick, fen, source = 'twic', onSourceChange }: MoveTreeProps) {
  // Parse move number and side to play from FEN
  const movePrefix = useMemo(() => {
    if (!fen) return '';
    const parts = fen.split(' ');
    const activeColor = parts[1]; // 'w' or 'b'
    const fullmove = parseInt(parts[5], 10) || 1;
    if (activeColor === 'b') {
      return `${fullmove}...`;
    }
    return `${fullmove}.`;
  }, [fen]);
  const [sortField, setSortField] = useState<SortField>('count');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [expanded, setExpanded] = useState(false);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(d => d === 'desc' ? 'asc' : 'desc');
    } else {
      setSortField(field);
      setSortDir(field === 'san' ? 'asc' : 'desc');
    }
  };

  // Reset expand when position changes
  React.useEffect(() => { setExpanded(false); }, [fen]);

  const sortedMoves = useMemo(() => {
    const sorted = [...moves];
    sorted.sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case 'san': cmp = a.san.localeCompare(b.san); break;
        case 'count': cmp = a.count - b.count; break;
        case 'percentage': cmp = a.percentage - b.percentage; break;
        case 'avg_elo': cmp = (a.avg_elo || 0) - (b.avg_elo || 0); break;
        case 'avg_year': cmp = (a.avg_year || 0) - (b.avg_year || 0); break;
      }
      return sortDir === 'desc' ? -cmp : cmp;
    });
    return sorted;
  }, [moves, sortField, sortDir]);

  const visibleMoves = expanded ? sortedMoves : sortedMoves.slice(0, DEFAULT_VISIBLE);
  const hasMore = sortedMoves.length > DEFAULT_VISIBLE;

  if (!loading && moves.length === 0) {
    return (
      <Box sx={{ py: 1.5, px: 1.5 }}>
        <Typography variant="caption" sx={{ color: 'var(--text-tertiary)', fontSize: 11, fontStyle: 'italic' }}>
          No moves found in database
        </Typography>
      </Box>
    );
  }

  const SortHeader = ({ field, label, align = 'left' as const, minW }: { field: SortField; label: string; align?: 'left' | 'right' | 'center'; minW?: number }) => (
    <Typography
      component="th"
      onClick={() => handleSort(field)}
      sx={{
        fontSize: 10,
        fontWeight: 600,
        color: sortField === field ? '#14b8a6' : 'var(--text-tertiary)',
        textTransform: 'uppercase' as const,
        letterSpacing: '0.5px',
        cursor: 'pointer',
        userSelect: 'none' as const,
        textAlign: align,
        py: 0.5,
        px: 0.5,
        minWidth: minW,
        whiteSpace: 'nowrap' as const,
        '&:hover': { color: '#2dd4bf' },
      }}
    >
      {label}
      {sortField === field && (sortDir === 'desc' ? ' ▾' : ' ▴')}
    </Typography>
  );

  return (
    <Box sx={{ overflow: 'auto', position: 'relative' }}>
      {loading && (
        <LinearProgress sx={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, '& .MuiLinearProgress-bar': { bgcolor: '#14b8a6' }, bgcolor: 'transparent' }} />
      )}

      {/* Source toggle dropdown */}
      {onSourceChange && (
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 0.5, px: 0.5 }}>
          <Select
            value={source}
            onChange={(e) => onSourceChange(e.target.value as MoveTreeSource)}
            size="small"
            sx={{
              fontSize: 11,
              fontWeight: 600,
              height: 24,
              '& .MuiSelect-select': { py: 0.3, px: 1 },
              '& .MuiOutlinedInput-notchedOutline': { borderColor: 'var(--border-subtle)' },
              '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#14b8a6' },
              '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: '#14b8a6' },
            }}
          >
            <MenuItem value="twic" sx={{ fontSize: 11 }}>Masters (TWIC)</MenuItem>
            <MenuItem value="lichess-masters" sx={{ fontSize: 11 }}>Lichess Masters</MenuItem>
            <MenuItem value="lichess-players" sx={{ fontSize: 11 }}>Lichess Players</MenuItem>
          </Select>
        </Box>
      )}

      <Box component="table" sx={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, opacity: loading ? 0.5 : 1, transition: 'opacity 0.15s ease' }}>
        <Box component="thead">
          <Box component="tr" sx={{ borderBottom: '1px solid var(--border-strong)' }}>
            <SortHeader field="san" label="Move" minW={48} />
            <SortHeader field="count" label="Games" align="right" minW={50} />
            <SortHeader field="percentage" label="%" align="right" minW={36} />
            <Typography component="th" sx={{ fontSize: 10, fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.5px', py: 0.5, px: 0.5, minWidth: 90, textAlign: 'center' }}>
              Score
            </Typography>
            <SortHeader field="avg_elo" label="AvElo" align="right" minW={44} />
            <SortHeader field="avg_year" label="AvYear" align="right" minW={44} />
          </Box>
        </Box>
        <Box component="tbody">
          {visibleMoves.map((move, idx) => {
            const total = move.white_wins + move.draws + move.black_wins;
            const wPct = total > 0 ? (move.white_wins / total) * 100 : 0;
            const dPct = total > 0 ? (move.draws / total) * 100 : 0;
            const bPct = total > 0 ? (move.black_wins / total) * 100 : 0;

            return (
              <Box
                component="tr"
                key={move.uci || idx}
                onClick={() => onMoveClick(move)}
                sx={{
                  cursor: 'pointer',
                  '&:hover': { bgcolor: 'rgba(31,41,55,0.04)' },
                  borderBottom: '1px solid var(--border-subtle, rgba(255,255,255,0.04))',
                }}
              >
                {/* Move */}
                <Box component="td" sx={{ py: 0.4, px: 0.5 }}>
                  <Typography
                    component="span"
                    sx={{
                      fontSize: 12,
                      fontWeight: 700,
                      color: idx === 0 ? '#0d9488' : 'var(--text-primary)',
                      fontFamily: 'monospace',
                    }}
                  >
                    {movePrefix && <Typography component="span" sx={{ fontSize: 11, fontWeight: 400, color: 'var(--text-tertiary)', fontFamily: 'monospace', mr: 0.3 }}>{movePrefix}</Typography>}{move.san}
                  </Typography>
                </Box>

                {/* Games */}
                <Box component="td" sx={{ py: 0.4, px: 0.5, textAlign: 'right' }}>
                  <Typography component="span" sx={{ fontSize: 11, color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
                    {move.count.toLocaleString()}
                  </Typography>
                </Box>

                {/* % */}
                <Box component="td" sx={{ py: 0.4, px: 0.5, textAlign: 'right' }}>
                  <Typography component="span" sx={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'monospace' }}>
                    {move.percentage.toFixed(0)}%
                  </Typography>
                </Box>

                {/* Score bar (W/D/B tri-color) */}
                <Box component="td" sx={{ py: 0.4, px: 0.5 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <Box
                      sx={{
                        display: 'flex',
                        width: '100%',
                        height: 10,
                        borderRadius: '2px',
                        overflow: 'hidden',
                        minWidth: 60,
                      }}
                    >
                      {/* White wins */}
                      <Box
                        sx={{
                          width: `${wPct}%`,
                          bgcolor: '#f0f0f0',
                          minWidth: wPct > 0 ? 1 : 0,
                        }}
                        title={`White: ${wPct.toFixed(1)}%`}
                      />
                      {/* Draws */}
                      <Box
                        sx={{
                          width: `${dPct}%`,
                          bgcolor: '#888',
                          minWidth: dPct > 0 ? 1 : 0,
                        }}
                        title={`Draw: ${dPct.toFixed(1)}%`}
                      />
                      {/* Black wins */}
                      <Box
                        sx={{
                          width: `${bPct}%`,
                          bgcolor: '#333',
                          minWidth: bPct > 0 ? 1 : 0,
                        }}
                        title={`Black: ${bPct.toFixed(1)}%`}
                      />
                    </Box>
                  </Box>
                </Box>

                {/* AvElo */}
                <Box component="td" sx={{ py: 0.4, px: 0.5, textAlign: 'right' }}>
                  <Typography component="span" sx={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'monospace' }}>
                    {move.avg_elo || '—'}
                  </Typography>
                </Box>

                {/* AvYear */}
                <Box component="td" sx={{ py: 0.4, px: 0.5, textAlign: 'right' }}>
                  <Typography component="span" sx={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'monospace' }}>
                    {move.avg_year || '—'}
                  </Typography>
                </Box>
              </Box>
            );
          })}
        </Box>
      </Box>
      {hasMore && (
        <Box
          onClick={() => setExpanded(e => !e)}
          sx={{
            display: 'flex',
            justifyContent: 'center',
            py: 0.5,
            cursor: 'pointer',
            userSelect: 'none',
            '&:hover': { bgcolor: 'rgba(31,41,55,0.04)' },
            borderTop: '1px solid var(--border-subtle, rgba(255,255,255,0.04))',
          }}
        >
          <Typography
            component="span"
            sx={{
              fontSize: 11,
              fontWeight: 600,
              color: '#14b8a6',
              '&:hover': { color: '#2dd4bf' },
            }}
          >
            {expanded ? 'Show less ▴' : `+${sortedMoves.length - DEFAULT_VISIBLE} more ▾`}
          </Typography>
        </Box>
      )}
    </Box>
  );
}
