/**
 * LichessExplorerTab — Lichess position search with Masters/Players toggle
 */

'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  Box,
  Typography,
  LinearProgress,
  Button,
  ToggleButton,
  ToggleButtonGroup,
  List,
  ListItem,
  ListItemText,
  Chip,
  IconButton,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import { ChevronLeft, ChevronRight, Refresh } from '@mui/icons-material';
import { useLichessExplorer, LichessExplorerResponse, LichessMove, LichessTopGame } from '@/hooks/useLichessExplorer';
import type { GameSearchResult } from '@/hooks/useOpeningRepertoire';
import GameCard from './GameCard';
import EmptyState from './EmptyState';

interface LichessExplorerTabProps {
  fen: string;
  database: 'masters' | 'lichess';
  onDatabaseChange: (db: 'masters' | 'lichess') => void;
  onOpenGame?: (game: GameSearchResult) => void;
}

const GAMES_PER_PAGE = 10;

export default function LichessExplorerTab({
  fen,
  database,
  onDatabaseChange,
  onOpenGame,
}: LichessExplorerTabProps) {
  const t = useTranslations('debut');
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [gamesPage, setGamesPage] = useState(0);

  const { data, loading, error, upstreamDown, retry } = useLichessExplorer({
    fen,
    database,
    enabled: true,
  });

  // Reset page when FEN or database changes
  useEffect(() => {
    setGamesPage(0);
  }, [fen, database]);

  // Transform LichessTopGame to GameSearchResult format
  const transformedGames = useMemo(() => {
    if (!data?.topGames) return [];
    return data.topGames.map((g: LichessTopGame): GameSearchResult => ({
      id: g.id,
      source: 'lichess',
      white: g.white.name,
      black: g.black.name,
      white_elo: g.white.rating,
      black_elo: g.black.rating,
      result: g.winner === 'white' ? '1-0' : g.winner === 'black' ? '0-1' : '½-½',
      date: g.year && g.month ? `${g.year}.${g.month}` : (g.year?.toString() || '?'),
      eco: null,
      opening: null,
      event: null,
      url: `https://lichess.org/${g.id}`,
    }));
  }, [data]);

  const visibleGames = transformedGames.slice(gamesPage * GAMES_PER_PAGE, (gamesPage + 1) * GAMES_PER_PAGE);
  const totalPages = Math.ceil(transformedGames.length / GAMES_PER_PAGE);

  // Move stats table
  const moveStats = useMemo(() => {
    if (!data?.moves) return [];
    return data.moves.map((m: LichessMove) => {
      const total = m.white + m.draws + m.black;
      return {
        san: m.san,
        count: total,
        percentage: total > 0 ? ((total / (data.white + data.draws + data.black)) * 100).toFixed(1) : '0',
        white_pct: total > 0 ? ((m.white / total) * 100).toFixed(1) : '0',
        draw_pct: total > 0 ? ((m.draws / total) * 100).toFixed(1) : '0',
        black_pct: total > 0 ? ((m.black / total) * 100).toFixed(1) : '0',
        avg_rating: m.averageRating || null,
      };
    });
  }, [data]);

  const totalGames = data ? data.white + data.draws + data.black : 0;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, py: 1 }}>
      {/* Database toggle */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <ToggleButtonGroup
          value={database}
          exclusive
          onChange={(_, val) => val && onDatabaseChange(val)}
          size="small"
          sx={{
            '& .MuiToggleButton-root': {
              fontSize: 11,
              fontWeight: 600,
              textTransform: 'none',
              px: 1.5,
              py: 0.5,
              color: 'text.secondary',
              '&.Mui-selected': {
                bgcolor: '#14b8a6',
                color: '#fff',
                '&:hover': { bgcolor: '#0d9488' },
              },
            },
          }}
        >
          <ToggleButton value="masters">Masters</ToggleButton>
          <ToggleButton value="lichess">Players</ToggleButton>
        </ToggleButtonGroup>
        {totalGames > 0 && (
          <Chip
            label={`${totalGames.toLocaleString()} games`}
            size="small"
            sx={{ height: 20, fontSize: 11, bgcolor: '#1f2937', color: '#fff', ml: 'auto' }}
          />
        )}
      </Box>

      {/* Loading state */}
      {loading && (
        <LinearProgress
          sx={{
            height: 2,
            '& .MuiLinearProgress-bar': { bgcolor: '#14b8a6' },
            bgcolor: 'rgba(20, 184, 166, 0.1)',
          }}
        />
      )}

      {/* Upstream down warning (amber) */}
      {upstreamDown && !loading && !error && (
        <Box sx={{ py: 1, px: 1.5, bgcolor: 'rgba(251, 191, 36, 0.1)', borderRadius: 1, border: '1px solid rgba(251, 191, 36, 0.4)' }}>
          <Typography variant="caption" sx={{ color: '#f59e0b', fontSize: 11, display: 'block', mb: 0.5 }}>
            ⚠️ Lichess Explorer is currently unavailable. Showing cached data if available.
          </Typography>
        </Box>
      )}

      {/* Error state */}
      {error && !loading && (
        <Box sx={{ py: 1, px: 1.5, bgcolor: 'rgba(239, 68, 68, 0.1)', borderRadius: 1, border: '1px solid rgba(239, 68, 68, 0.3)' }}>
          <Typography variant="caption" sx={{ color: '#ef4444', fontSize: 11, display: 'block', mb: 0.5 }}>
            Failed to load Lichess data
          </Typography>
          <Button
            size="small"
            startIcon={<Refresh sx={{ fontSize: 14 }} />}
            onClick={retry}
            sx={{ fontSize: 10, textTransform: 'none', color: '#ef4444', minHeight: 0, py: 0.3 }}
          >
            Retry
          </Button>
        </Box>
      )}

      {/* Move stats table */}
      {!loading && !error && moveStats.length > 0 && (
        <Box>
          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textTransform: 'uppercase', fontSize: 11, mb: 0.5, display: 'block' }}>
            Move Statistics
          </Typography>
          <Box component="table" sx={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
            <Box component="thead">
              <Box component="tr" sx={{ borderBottom: '1px solid var(--border-strong)' }}>
                <Typography component="th" sx={{ fontSize: 10, fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.5px', py: 0.5, px: 0.5, textAlign: 'left' }}>
                  Move
                </Typography>
                <Typography component="th" sx={{ fontSize: 10, fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.5px', py: 0.5, px: 0.5, textAlign: 'right' }}>
                  Games
                </Typography>
                <Typography component="th" sx={{ fontSize: 10, fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.5px', py: 0.5, px: 0.5, textAlign: 'center', minWidth: 90 }}>
                  Score
                </Typography>
                {database === 'masters' && (
                  <Typography component="th" sx={{ fontSize: 10, fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.5px', py: 0.5, px: 0.5, textAlign: 'right' }}>
                    Avg Elo
                  </Typography>
                )}
              </Box>
            </Box>
            <Box component="tbody">
              {moveStats.slice(0, 8).map((stat, idx) => (
                <Box
                  component="tr"
                  key={idx}
                  sx={{
                    borderBottom: '1px solid var(--border-subtle, rgba(255,255,255,0.04))',
                  }}
                >
                  <Box component="td" sx={{ py: 0.4, px: 0.5 }}>
                    <Typography component="span" sx={{ fontSize: 12, fontWeight: 700, color: idx === 0 ? '#0d9488' : 'var(--text-primary)', fontFamily: 'monospace' }}>
                      {stat.san}
                    </Typography>
                  </Box>
                  <Box component="td" sx={{ py: 0.4, px: 0.5, textAlign: 'right' }}>
                    <Typography component="span" sx={{ fontSize: 11, color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
                      {stat.count}
                    </Typography>
                  </Box>
                  <Box component="td" sx={{ py: 0.4, px: 0.5 }}>
                    <Box sx={{ display: 'flex', width: '100%', height: 10, borderRadius: '2px', overflow: 'hidden', minWidth: 60 }}>
                      <Box sx={{ width: `${stat.white_pct}%`, bgcolor: '#f0f0f0', minWidth: parseFloat(stat.white_pct) > 0 ? 1 : 0 }} title={`White: ${stat.white_pct}%`} />
                      <Box sx={{ width: `${stat.draw_pct}%`, bgcolor: '#888', minWidth: parseFloat(stat.draw_pct) > 0 ? 1 : 0 }} title={`Draw: ${stat.draw_pct}%`} />
                      <Box sx={{ width: `${stat.black_pct}%`, bgcolor: '#333', minWidth: parseFloat(stat.black_pct) > 0 ? 1 : 0 }} title={`Black: ${stat.black_pct}%`} />
                    </Box>
                  </Box>
                  {database === 'masters' && (
                    <Box component="td" sx={{ py: 0.4, px: 0.5, textAlign: 'right' }}>
                      <Typography component="span" sx={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'monospace' }}>
                        {stat.avg_rating || '—'}
                      </Typography>
                    </Box>
                  )}
                </Box>
              ))}
            </Box>
          </Box>
        </Box>
      )}

      {/* Games list - card layout on mobile, list on desktop */}
      {!loading && !error && transformedGames.length > 0 && (
        <Box>
          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textTransform: 'uppercase', fontSize: 11, mb: 0.5, display: 'block' }}>
            Top Games
          </Typography>

          {isMobile ? (
            // Mobile: Card layout
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              {visibleGames.map((g) => (
                <GameCard
                  key={g.id}
                  game={g}
                  onClick={() => onOpenGame?.(g)}
                />
              ))}
            </Box>
          ) : (
            // Desktop: List layout
            <List dense sx={{ p: 0 }}>
              {visibleGames.map((g) => (
                <ListItem
                  key={g.id}
                  sx={{ px: 0, py: 0.3, cursor: onOpenGame ? 'pointer' : 'default', '&:hover': onOpenGame ? { bgcolor: 'rgba(255,255,255,0.04)' } : {} }}
                  onClick={() => onOpenGame?.(g)}
                >
                  <ListItemText
                    primary={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <Typography component="span" sx={{ color: 'text.primary', fontSize: 12 }}>
                          {g.white}
                        </Typography>
                        <Typography component="span" sx={{ color: 'text.secondary', fontSize: 10 }}>
                          ({g.white_elo || '?'})
                        </Typography>
                        <Typography component="span" sx={{ color: 'text.secondary', fontSize: 11 }}>{t('vs')}</Typography>
                        <Typography component="span" sx={{ color: 'text.primary', fontSize: 12 }}>
                          {g.black}
                        </Typography>
                        <Typography component="span" sx={{ color: 'text.secondary', fontSize: 10 }}>
                          ({g.black_elo || '?'})
                        </Typography>
                      </Box>
                    }
                    secondary={
                      <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', mt: 0.2 }}>
                        <Chip label={g.result} size="small" sx={{ height: 14, fontSize: 9, bgcolor: 'action.hover', color: 'text.secondary' }} />
                        <Typography component="span" sx={{ color: 'text.secondary', fontSize: 10 }}>
                          {g.date}
                        </Typography>
                      </Box>
                    }
                  />
                </ListItem>
              ))}
            </List>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1, mt: 0.5 }}>
              <IconButton
                size="small"
                disabled={gamesPage === 0}
                onClick={() => setGamesPage((p) => p - 1)}
                sx={{ color: 'text.secondary', p: 0.3 }}
              >
                <ChevronLeft sx={{ fontSize: 18 }} />
              </IconButton>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 11 }}>
                {gamesPage + 1} / {totalPages}
              </Typography>
              <IconButton
                size="small"
                disabled={gamesPage + 1 >= totalPages}
                onClick={() => setGamesPage((p) => p + 1)}
                sx={{ color: 'text.secondary', p: 0.3 }}
              >
                <ChevronRight sx={{ fontSize: 18 }} />
              </IconButton>
            </Box>
          )}
        </Box>
      )}

      {/* Empty state */}
      {!loading && !error && totalGames === 0 && (
        <EmptyState type="no-games" />
      )}
    </Box>
  );
}
