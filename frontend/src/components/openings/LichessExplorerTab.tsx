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
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import { ChevronLeft, ChevronRight, Refresh, Search } from '@mui/icons-material';
import { useLichessExplorer, LichessExplorerResponse, LichessMove, LichessTopGame } from '@/hooks/useLichessExplorer';
import type { GameSearchResult } from '@/hooks/useOpeningRepertoire';
import GameCard from './GameCard';
import EmptyState from './EmptyState';

interface LichessExplorerTabProps {
  fen: string;
  database: 'masters' | 'lichess' | 'player';
  onDatabaseChange: (db: 'masters' | 'lichess' | 'player') => void;
  onOpenGame?: (game: GameSearchResult) => void;
}

const GAMES_PER_PAGE = 10;

const DEFAULT_RATINGS = ['1600', '1800', '2000', '2200', '2500'];
const DEFAULT_SPEEDS = ['blitz', 'rapid', 'classical'];

const ALL_RATINGS = ['1000', '1200', '1400', '1600', '1800', '2000', '2200', '2500'];
const ALL_SPEEDS = ['ultraBullet', 'bullet', 'blitz', 'rapid', 'classical', 'correspondence'];

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

  // Player filter state (only for lichess database)
  const [selectedRatings, setSelectedRatings] = useState<string[]>(DEFAULT_RATINGS);
  const [selectedSpeeds, setSelectedSpeeds] = useState<string[]>(DEFAULT_SPEEDS);

  // Player search state (only for player database)
  const [username, setUsername] = useState('');
  const [searchUsername, setSearchUsername] = useState('');
  const [playerColor, setPlayerColor] = useState<'white' | 'black'>('white');
  const [playerSpeeds, setPlayerSpeeds] = useState<string[]>(DEFAULT_SPEEDS);
  const [playerMode, setPlayerMode] = useState<string>('rated');
  const [recentGamesCount, setRecentGamesCount] = useState<number>(8);

  const { data, loading, error, upstreamDown, retry } = useLichessExplorer({
    fen,
    database,
    enabled: database === 'player' ? !!searchUsername : true,
    ratings: database === 'lichess' ? selectedRatings.join(',') : undefined,
    speeds: database === 'lichess' ? selectedSpeeds.join(',') : database === 'player' ? playerSpeeds.join(',') : undefined,
    player: database === 'player' ? searchUsername : undefined,
    color: database === 'player' ? playerColor : undefined,
    modes: database === 'player' ? playerMode : undefined,
    recentGames: database === 'player' ? recentGamesCount : undefined,
  });

  // Reset page when FEN or database changes
  useEffect(() => {
    setGamesPage(0);
  }, [fen, database]);

  // Reset filters to defaults when switching databases
  useEffect(() => {
    if (database === 'lichess') {
      setSelectedRatings(DEFAULT_RATINGS);
      setSelectedSpeeds(DEFAULT_SPEEDS);
    } else if (database === 'player') {
      setPlayerSpeeds(DEFAULT_SPEEDS);
      setPlayerMode('rated');
      setRecentGamesCount(8);
    }
  }, [database]);

  // Handle rating toggle
  const toggleRating = (rating: string) => {
    setSelectedRatings((prev) =>
      prev.includes(rating) ? prev.filter((r) => r !== rating) : [...prev, rating].sort()
    );
  };

  // Handle speed toggle
  const toggleSpeed = (speed: string) => {
    setSelectedSpeeds((prev) =>
      prev.includes(speed) ? prev.filter((s) => s !== speed) : [...prev, speed]
    );
  };

  // Handle player speed toggle
  const togglePlayerSpeed = (speed: string) => {
    setPlayerSpeeds((prev) =>
      prev.includes(speed) ? prev.filter((s) => s !== speed) : [...prev, speed]
    );
  };

  // Handle player search
  const handleSearch = () => {
    if (username.trim()) {
      setSearchUsername(username.trim());
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

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
          <ToggleButton value="masters">{t('lichessDatabase.masters')}</ToggleButton>
          <ToggleButton value="lichess">{t('lichessDatabase.players')}</ToggleButton>
          <ToggleButton value="player">{t('lichessDatabase.player')}</ToggleButton>
        </ToggleButtonGroup>
        {totalGames > 0 && (
          <Chip
            label={`${totalGames.toLocaleString()} games`}
            size="small"
            sx={{ height: 20, fontSize: 11, bgcolor: '#1f2937', color: '#fff', ml: 'auto' }}
          />
        )}
      </Box>

      {/* Player username search - only show for player database */}
      {database === 'player' && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <TextField
            size="small"
            placeholder={t('lichessPlayer.usernamePlaceholder')}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            onKeyDown={handleKeyDown}
            sx={{
              flex: 1,
              '& .MuiInputBase-root': {
                fontSize: 12,
                height: 32,
                bgcolor: 'rgba(255,255,255,0.03)',
                color: 'text.primary',
                borderRadius: 1,
              },
              '& .MuiOutlinedInput-notchedOutline': {
                borderColor: 'rgba(255,255,255,0.1)',
              },
              '& .MuiInputBase-input::placeholder': {
                color: 'text.secondary',
                opacity: 0.7,
              },
            }}
          />
          <Button
            size="small"
            variant="contained"
            startIcon={<Search sx={{ fontSize: 14 }} />}
            onClick={handleSearch}
            disabled={loading}
            sx={{
              height: 32,
              fontSize: 11,
              fontWeight: 600,
              textTransform: 'none',
              bgcolor: '#14b8a6',
              color: '#fff',
              '&:hover': { bgcolor: '#0d9488' },
              '&:disabled': { bgcolor: 'rgba(20, 184, 166, 0.3)' },
              px: 1.5,
            }}
          >
            {t('lichessPlayer.search')}
          </Button>
        </Box>
      )}

      {/* Player filters - only show for player database with username */}
      {database === 'player' && searchUsername && (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, py: 0.5 }}>
          {/* Color selector */}
          <Box>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, fontSize: 10, textTransform: 'uppercase', mb: 0.5, display: 'block' }}>
              {t('lichessPlayer.color')}
            </Typography>
            <ToggleButtonGroup
              value={playerColor}
              exclusive
              onChange={(_, val) => val && setPlayerColor(val)}
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
              <ToggleButton value="white">{t('lichessPlayer.white')}</ToggleButton>
              <ToggleButton value="black">{t('lichessPlayer.black')}</ToggleButton>
            </ToggleButtonGroup>
          </Box>

          {/* Speed filters */}
          <Box>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, fontSize: 10, textTransform: 'uppercase', mb: 0.5, display: 'block' }}>
              {t('lichessFilters.speed')}
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
              {ALL_SPEEDS.map((speed) => (
                <Chip
                  key={speed}
                  label={t(`lichessFilters.speeds.${speed}`)}
                  size="small"
                  onClick={() => togglePlayerSpeed(speed)}
                  sx={{
                    height: 22,
                    fontSize: 10,
                    fontWeight: 600,
                    cursor: 'pointer',
                    bgcolor: playerSpeeds.includes(speed) ? '#14b8a6' : 'rgba(255,255,255,0.08)',
                    color: playerSpeeds.includes(speed) ? '#fff' : 'text.secondary',
                    '&:hover': {
                      bgcolor: playerSpeeds.includes(speed) ? '#0d9488' : 'rgba(255,255,255,0.12)',
                    },
                  }}
                />
              ))}
            </Box>
          </Box>

          {/* Mode selector and Recent games count */}
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: { xs: 'wrap', sm: 'nowrap' } }}>
            <FormControl size="small" sx={{ minWidth: { xs: '48%', sm: 100 } }}>
              <InputLabel sx={{ fontSize: 11, color: 'text.secondary' }}>{t('lichessPlayer.mode')}</InputLabel>
              <Select
                value={playerMode}
                onChange={(e) => setPlayerMode(e.target.value)}
                label={t('lichessPlayer.mode')}
                sx={{
                  fontSize: 11,
                  height: 32,
                  bgcolor: 'rgba(255,255,255,0.03)',
                  color: 'text.primary',
                  '& .MuiOutlinedInput-notchedOutline': {
                    borderColor: 'rgba(255,255,255,0.1)',
                  },
                }}
              >
                <MenuItem value="rated" sx={{ fontSize: 11 }}>{t('lichessPlayer.rated')}</MenuItem>
                <MenuItem value="casual" sx={{ fontSize: 11 }}>{t('lichessPlayer.casual')}</MenuItem>
                <MenuItem value="rated,casual" sx={{ fontSize: 11 }}>{t('lichessPlayer.both')}</MenuItem>
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: { xs: '48%', sm: 100 } }}>
              <InputLabel sx={{ fontSize: 11, color: 'text.secondary' }}>{t('lichessPlayer.recentGames')}</InputLabel>
              <Select
                value={recentGamesCount}
                onChange={(e) => setRecentGamesCount(e.target.value as number)}
                label={t('lichessPlayer.recentGames')}
                sx={{
                  fontSize: 11,
                  height: 32,
                  bgcolor: 'rgba(255,255,255,0.03)',
                  color: 'text.primary',
                  '& .MuiOutlinedInput-notchedOutline': {
                    borderColor: 'rgba(255,255,255,0.1)',
                  },
                }}
              >
                <MenuItem value={4} sx={{ fontSize: 11 }}>4</MenuItem>
                <MenuItem value={8} sx={{ fontSize: 11 }}>8</MenuItem>
                <MenuItem value={12} sx={{ fontSize: 11 }}>12</MenuItem>
                <MenuItem value={15} sx={{ fontSize: 11 }}>15</MenuItem>
              </Select>
            </FormControl>
          </Box>
        </Box>
      )}

      {/* Player filters - only show for lichess database */}
      {database === 'lichess' && (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, py: 0.5 }}>
          {/* Rating filters */}
          <Box>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, fontSize: 10, textTransform: 'uppercase', mb: 0.5, display: 'block' }}>
              {t('lichessFilters.rating')}
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
              {ALL_RATINGS.map((rating) => (
                <Chip
                  key={rating}
                  label={`${rating}+`}
                  size="small"
                  onClick={() => toggleRating(rating)}
                  sx={{
                    height: 22,
                    fontSize: 10,
                    fontWeight: 600,
                    cursor: 'pointer',
                    bgcolor: selectedRatings.includes(rating) ? '#14b8a6' : 'rgba(255,255,255,0.08)',
                    color: selectedRatings.includes(rating) ? '#fff' : 'text.secondary',
                    '&:hover': {
                      bgcolor: selectedRatings.includes(rating) ? '#0d9488' : 'rgba(255,255,255,0.12)',
                    },
                  }}
                />
              ))}
            </Box>
          </Box>

          {/* Speed filters */}
          <Box>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, fontSize: 10, textTransform: 'uppercase', mb: 0.5, display: 'block' }}>
              {t('lichessFilters.speed')}
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
              {ALL_SPEEDS.map((speed) => (
                <Chip
                  key={speed}
                  label={t(`lichessFilters.speeds.${speed}`)}
                  size="small"
                  onClick={() => toggleSpeed(speed)}
                  sx={{
                    height: 22,
                    fontSize: 10,
                    fontWeight: 600,
                    cursor: 'pointer',
                    bgcolor: selectedSpeeds.includes(speed) ? '#14b8a6' : 'rgba(255,255,255,0.08)',
                    color: selectedSpeeds.includes(speed) ? '#fff' : 'text.secondary',
                    '&:hover': {
                      bgcolor: selectedSpeeds.includes(speed) ? '#0d9488' : 'rgba(255,255,255,0.12)',
                    },
                  }}
                />
              ))}
            </Box>
          </Box>
        </Box>
      )}

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

      {/* Empty state - no username for player database */}
      {!loading && !error && database === 'player' && !searchUsername && (
        <EmptyState
          type="position-search-unavailable"
          message={t('lichessPlayer.enterUsername')}
          hint={t('lichessPlayer.enterUsernameHint')}
        />
      )}

      {/* Empty state - no games found */}
      {!loading && !error && totalGames === 0 && (database !== 'player' || searchUsername) && (
        <EmptyState type="no-games" />
      )}
    </Box>
  );
}
