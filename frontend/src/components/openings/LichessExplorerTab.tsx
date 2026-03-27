/**
 * LichessExplorerTab — Lichess position search with Masters/Lichess toggle
 * Masters: OTB master games
 * Lichess: All Lichess games (aggregate stats + optional player search)
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
  Divider,
  Collapse,
} from '@mui/material';
import { ChevronLeft, ChevronRight, Refresh, Search, FilterList } from '@mui/icons-material';
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

const DEFAULT_SPEEDS = ['blitz', 'rapid', 'classical'];

const ALL_SPEEDS = ['ultraBullet', 'bullet', 'blitz', 'rapid', 'classical', 'correspondence'];
const ALL_RATINGS = ['1000', '1200', '1400', '1600', '1800', '2000', '2200', '2500'];

export default function LichessExplorerTab({
  fen,
  database,
  onDatabaseChange,
  onOpenGame,
}: LichessExplorerTabProps) {
  const t = useTranslations('debut');
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [aggregateGamesPage, setAggregateGamesPage] = useState(0);
  const [playerGamesPage, setPlayerGamesPage] = useState(0);
  const [filtersOpen, setFiltersOpen] = useState(!isMobile); // Collapsed by default on mobile

  // Aggregate lichess filter state (only for database='lichess')
  const [minRating, setMinRating] = useState<string>('1000');
  const [maxRating, setMaxRating] = useState<string>('2500');
  const [selectedSpeeds, setSelectedSpeeds] = useState<string[]>(DEFAULT_SPEEDS);

  // Player search state (only for database='lichess')
  const [username, setUsername] = useState('');
  const [searchUsername, setSearchUsername] = useState('');
  const [playerColor, setPlayerColor] = useState<string>('white'); // white/black/'' for any
  const [playerResultFilter, setPlayerResultFilter] = useState<string>(''); // win/draw/loss/'' for any
  const [playerSpeeds, setPlayerSpeeds] = useState<string[]>(DEFAULT_SPEEDS);
  const [playerMode, setPlayerMode] = useState<string>('rated');
  const [recentGamesCount, setRecentGamesCount] = useState<number>(8);

  // Compute selected rating ranges based on min/max rating
  const selectedRatings = useMemo(() => {
    const minIdx = ALL_RATINGS.indexOf(minRating);
    const maxIdx = ALL_RATINGS.indexOf(maxRating);
    if (minIdx === -1 || maxIdx === -1) return [];
    return ALL_RATINGS.slice(minIdx, maxIdx + 1);
  }, [minRating, maxRating]);

  // Aggregate query (masters or lichess aggregate)
  const { data: aggregateData, loading: aggregateLoading, error: aggregateError, upstreamDown: aggregateUpstreamDown, retry: retryAggregate } = useLichessExplorer({
    fen,
    database,
    enabled: true,
    ratings: database === 'lichess' ? selectedRatings.join(',') : undefined,
    speeds: database === 'lichess' ? selectedSpeeds.join(',') : undefined,
  });

  // Player query (only enabled when lichess + username entered)
  const { data: playerData, loading: playerLoading, error: playerError, upstreamDown: playerUpstreamDown, retry: retryPlayer } = useLichessExplorer({
    fen,
    database: 'player',
    enabled: database === 'lichess' && !!searchUsername,
    player: searchUsername,
    color: playerColor as 'white' | 'black',
    speeds: playerSpeeds.join(','),
    modes: playerMode,
    recentGames: recentGamesCount,
  });

  // Reset pages when FEN or database changes
  useEffect(() => {
    setAggregateGamesPage(0);
    setPlayerGamesPage(0);
  }, [fen, database]);

  // Reset filters to defaults when switching databases
  useEffect(() => {
    if (database === 'lichess') {
      setMinRating('1000');
      setMaxRating('2500');
      setSelectedSpeeds(DEFAULT_SPEEDS);
      setPlayerSpeeds(DEFAULT_SPEEDS);
      setPlayerMode('rated');
      setRecentGamesCount(8);
      setPlayerColor('white');
      setPlayerResultFilter('');
    }
  }, [database]);

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
  const transformGames = (games: LichessTopGame[]): GameSearchResult[] => {
    return games.map((g): GameSearchResult => ({
      id: g.id,
      source: 'lichess',
      white: g.white.name,
      black: g.black.name,
      white_elo: g.white.rating,
      black_elo: g.black.rating,
      result: g.winner === 'white' ? '1-0' : g.winner === 'black' ? '0-1' : '½-½',
      date: g.month ? g.month : (g.year?.toString() || '?'),
      eco: null,
      opening: null,
      event: null,
      url: `https://lichess.org/${g.id}`,
    }));
  };

  const aggregateGames = useMemo(() => transformGames(aggregateData?.topGames || []), [aggregateData]);

  // Client-side filtering for player result filter
  const playerGames = useMemo(() => {
    let games = transformGames(playerData?.topGames || []);

    if (playerResultFilter && searchUsername) {
      const uLower = searchUsername.toLowerCase();
      games = games.filter((g) => {
        const isWhite = g.white?.toLowerCase() === uLower;
        if (playerResultFilter === 'win') return (isWhite && g.result === '1-0') || (!isWhite && g.result === '0-1');
        if (playerResultFilter === 'loss') return (isWhite && g.result === '0-1') || (!isWhite && g.result === '1-0');
        if (playerResultFilter === 'draw') return g.result === '½-½' || g.result === '1/2-1/2';
        return true;
      });
    }

    return games;
  }, [playerData, playerResultFilter, searchUsername]);

  const visibleAggregateGames = aggregateGames.slice(aggregateGamesPage * GAMES_PER_PAGE, (aggregateGamesPage + 1) * GAMES_PER_PAGE);
  const visiblePlayerGames = playerGames.slice(playerGamesPage * GAMES_PER_PAGE, (playerGamesPage + 1) * GAMES_PER_PAGE);

  const totalAggregatePages = Math.ceil(aggregateGames.length / GAMES_PER_PAGE);
  const totalPlayerPages = Math.ceil(playerGames.length / GAMES_PER_PAGE);

  // Move stats rendering helper
  const renderMoveStats = (data: LichessExplorerResponse | null, loading: boolean, showAvgRating: boolean) => {
    if (!data?.moves || data.moves.length === 0) return null;

    const moves = data.moves.map((m: LichessMove) => {
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

    return (
      <Box sx={{ opacity: loading ? 0.5 : 1, transition: 'opacity 0.15s ease' }}>
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
              {showAvgRating && (
                <Typography component="th" sx={{ fontSize: 10, fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.5px', py: 0.5, px: 0.5, textAlign: 'right' }}>
                  Avg Elo
                </Typography>
              )}
            </Box>
          </Box>
          <Box component="tbody">
            {moves.slice(0, 8).map((stat, idx) => (
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
                {showAvgRating && (
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
    );
  };

  // Games list rendering helper
  const renderGamesList = (games: GameSearchResult[], page: number, totalPages: number, setPage: (p: number) => void, loading: boolean) => {
    if (games.length === 0) return null;

    const visibleGames = games.slice(page * GAMES_PER_PAGE, (page + 1) * GAMES_PER_PAGE);

    return (
      <Box sx={{ opacity: loading ? 0.5 : 1, transition: 'opacity 0.15s ease' }}>
        <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textTransform: 'uppercase', fontSize: 11, mb: 0.5, display: 'block' }}>
          {games.length < 5 && games.length > 0 ? `Top Games (showing all ${games.length} available)` : 'Top Games'}
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
              disabled={page === 0}
              onClick={() => setPage(page - 1)}
              sx={{ color: 'text.secondary', p: 0.3 }}
            >
              <ChevronLeft sx={{ fontSize: 18 }} />
            </IconButton>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 11 }}>
              {page + 1} / {totalPages}
            </Typography>
            <IconButton
              size="small"
              disabled={page + 1 >= totalPages}
              onClick={() => setPage(page + 1)}
              sx={{ color: 'text.secondary', p: 0.3 }}
            >
              <ChevronRight sx={{ fontSize: 18 }} />
            </IconButton>
          </Box>
        )}
      </Box>
    );
  };

  const aggregateTotalGames = aggregateData ? aggregateData.white + aggregateData.draws + aggregateData.black : 0;
  const playerTotalGames = playerData ? playerData.white + playerData.draws + playerData.black : 0;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, py: 1 }}>
      {/* Database toggle (2-way: Masters | Lichess) */}
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
        </ToggleButtonGroup>
        {aggregateTotalGames > 0 && (
          <Chip
            label={`${aggregateTotalGames.toLocaleString()} games`}
            size="small"
            sx={{ height: 20, fontSize: 11, bgcolor: '#1f2937', color: '#fff', ml: 'auto' }}
          />
        )}
      </Box>

      {/* Player username search field - only show for lichess database */}
      {database === 'lichess' && (
        <Box>
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
              disabled={playerLoading}
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

          {/* Color and Result filters - visible when username is entered */}
          {searchUsername && (
            <Box sx={{ display: 'flex', gap: 1, mt: 1, flexWrap: 'wrap' }}>
              <FormControl size="small" sx={{ minWidth: 100 }}>
                <Select
                  value={playerColor}
                  onChange={(e) => setPlayerColor(e.target.value)}
                  displayEmpty
                  sx={{
                    fontSize: 11,
                    height: 32,
                    bgcolor: 'rgba(255,255,255,0.03)',
                    color: 'text.primary',
                    '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.1)' },
                  }}
                >
                  <MenuItem value="white" sx={{ fontSize: 11 }}>{t('lichessPlayer.white')}</MenuItem>
                  <MenuItem value="black" sx={{ fontSize: 11 }}>{t('lichessPlayer.black')}</MenuItem>
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 100 }}>
                <Select
                  value={playerResultFilter}
                  onChange={(e) => setPlayerResultFilter(e.target.value)}
                  displayEmpty
                  sx={{
                    fontSize: 11,
                    height: 32,
                    bgcolor: 'rgba(255,255,255,0.03)',
                    color: 'text.primary',
                    '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.1)' },
                  }}
                >
                  <MenuItem value="" sx={{ fontSize: 11 }}>{t('anyResult', { defaultMessage: 'Any result' })}</MenuItem>
                  <MenuItem value="win" sx={{ fontSize: 11 }}>{t('onlineSearchFilters.resultWin', { defaultMessage: 'Win' })}</MenuItem>
                  <MenuItem value="draw" sx={{ fontSize: 11 }}>{t('onlineSearchFilters.resultDraw', { defaultMessage: 'Draw' })}</MenuItem>
                  <MenuItem value="loss" sx={{ fontSize: 11 }}>{t('onlineSearchFilters.resultLoss', { defaultMessage: 'Loss' })}</MenuItem>
                </Select>
              </FormControl>
            </Box>
          )}
        </Box>
      )}

      {/* Aggregate filters - only show for lichess database */}
      {database === 'lichess' && (
        <Box>
          {/* Filter toggle button (mobile only) */}
          {isMobile && (
            <Button
              size="small"
              startIcon={<FilterList sx={{ fontSize: 14 }} />}
              onClick={() => setFiltersOpen(!filtersOpen)}
              sx={{
                fontSize: 11,
                textTransform: 'none',
                color: 'text.secondary',
                mb: filtersOpen ? 0.5 : 0,
              }}
            >
              Filters
            </Button>
          )}

          <Collapse in={filtersOpen} timeout="auto">
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: { xs: 'wrap', sm: 'nowrap' } }}>
              {/* Rating Range - From */}
              <FormControl size="small" sx={{ minWidth: { xs: '48%', sm: 100 } }}>
                <InputLabel sx={{ fontSize: 11, color: 'text.secondary' }}>Min Rating</InputLabel>
                <Select
                  value={minRating}
                  onChange={(e) => {
                    const newMin = e.target.value;
                    setMinRating(newMin);
                    // If new min is greater than max, adjust max
                    if (ALL_RATINGS.indexOf(newMin) > ALL_RATINGS.indexOf(maxRating)) {
                      setMaxRating(newMin);
                    }
                  }}
                  label="Min Rating"
                  sx={{
                    fontSize: 11,
                    height: 32,
                    bgcolor: 'rgba(255,255,255,0.03)',
                    color: 'text.primary',
                    '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.1)' },
                  }}
                >
                  {ALL_RATINGS.map((rating) => (
                    <MenuItem key={rating} value={rating} sx={{ fontSize: 11 }}>
                      {rating}+
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              {/* Rating Range - To */}
              <FormControl size="small" sx={{ minWidth: { xs: '48%', sm: 100 } }}>
                <InputLabel sx={{ fontSize: 11, color: 'text.secondary' }}>Max Rating</InputLabel>
                <Select
                  value={maxRating}
                  onChange={(e) => {
                    const newMax = e.target.value;
                    setMaxRating(newMax);
                    // If new max is less than min, adjust min
                    if (ALL_RATINGS.indexOf(newMax) < ALL_RATINGS.indexOf(minRating)) {
                      setMinRating(newMax);
                    }
                  }}
                  label="Max Rating"
                  sx={{
                    fontSize: 11,
                    height: 32,
                    bgcolor: 'rgba(255,255,255,0.03)',
                    color: 'text.primary',
                    '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.1)' },
                  }}
                >
                  {ALL_RATINGS.map((rating) => (
                    <MenuItem key={rating} value={rating} sx={{ fontSize: 11 }}>
                      {rating}+
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              {/* Speed Filter - Multi-select */}
              <FormControl size="small" sx={{ minWidth: { xs: '100%', sm: 120 } }}>
                <InputLabel sx={{ fontSize: 11, color: 'text.secondary' }}>Speed</InputLabel>
                <Select
                  multiple
                  value={selectedSpeeds}
                  onChange={(e) => setSelectedSpeeds(e.target.value as string[])}
                  label="Speed"
                  renderValue={(selected) => `${selected.length} selected`}
                  sx={{
                    fontSize: 11,
                    height: 32,
                    bgcolor: 'rgba(255,255,255,0.03)',
                    color: 'text.primary',
                    '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.1)' },
                  }}
                >
                  {ALL_SPEEDS.map((speed) => (
                    <MenuItem key={speed} value={speed} sx={{ fontSize: 11 }}>
                      <Chip
                        label={t(`lichessFilters.speeds.${speed}`)}
                        size="small"
                        sx={{
                          height: 18,
                          fontSize: 9,
                          bgcolor: selectedSpeeds.includes(speed) ? '#14b8a6' : 'rgba(255,255,255,0.08)',
                          color: selectedSpeeds.includes(speed) ? '#fff' : 'text.secondary',
                        }}
                      />
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              {aggregateTotalGames > 0 && !isMobile && (
                <Chip
                  label={`${aggregateTotalGames.toLocaleString()} games`}
                  size="small"
                  sx={{ height: 20, fontSize: 11, bgcolor: '#1f2937', color: '#fff', ml: 'auto' }}
                />
              )}
            </Box>
          </Collapse>
        </Box>
      )}

      {/* Loading state */}
      {aggregateLoading && (
        <LinearProgress
          sx={{
            height: 2,
            '& .MuiLinearProgress-bar': { bgcolor: '#14b8a6' },
            bgcolor: 'rgba(20, 184, 166, 0.1)',
          }}
        />
      )}

      {/* Upstream down warning (amber) */}
      {aggregateUpstreamDown && !aggregateLoading && !aggregateError && (
        <Box sx={{ py: 1, px: 1.5, bgcolor: 'rgba(251, 191, 36, 0.1)', borderRadius: 1, border: '1px solid rgba(251, 191, 36, 0.4)' }}>
          <Typography variant="caption" sx={{ color: '#f59e0b', fontSize: 11, display: 'block', mb: 0.5 }}>
            ⚠️ Lichess Explorer is currently unavailable. Showing cached data if available.
          </Typography>
        </Box>
      )}

      {/* Error state */}
      {aggregateError && !aggregateLoading && (
        <Box sx={{ py: 1, px: 1.5, bgcolor: 'rgba(239, 68, 68, 0.1)', borderRadius: 1, border: '1px solid rgba(239, 68, 68, 0.3)' }}>
          <Typography variant="caption" sx={{ color: '#ef4444', fontSize: 11, display: 'block', mb: 0.5 }}>
            Failed to load Lichess data
          </Typography>
          <Button
            size="small"
            startIcon={<Refresh sx={{ fontSize: 14 }} />}
            onClick={retryAggregate}
            sx={{ fontSize: 10, textTransform: 'none', color: '#ef4444', minHeight: 0, py: 0.3 }}
          >
            Retry
          </Button>
        </Box>
      )}

      {/* Aggregate move stats table */}
      {!aggregateLoading && !aggregateError && aggregateData && (
        renderMoveStats(aggregateData, aggregateLoading, database === 'masters')
      )}

      {/* Aggregate games list */}
      {!aggregateLoading && !aggregateError && aggregateGames.length > 0 && (
        renderGamesList(aggregateGames, aggregateGamesPage, totalAggregatePages, setAggregateGamesPage, aggregateLoading)
      )}

      {/* Empty state for aggregate - no games found */}
      {!aggregateLoading && !aggregateError && aggregateTotalGames === 0 && (
        <EmptyState type="no-games" />
      )}

      {/* Player filters & results - only show for lichess database */}
      {database === 'lichess' && (
        <>
          {/* Player filters - only show when username is searched */}
          {searchUsername && (
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: { xs: 'wrap', sm: 'nowrap' }, mt: 1 }}>
              {/* Speed Filter - Multi-select */}
              <FormControl size="small" sx={{ minWidth: { xs: '100%', sm: 120 } }}>
                <InputLabel sx={{ fontSize: 11, color: 'text.secondary' }}>Speed</InputLabel>
                <Select
                  multiple
                  value={playerSpeeds}
                  onChange={(e) => setPlayerSpeeds(e.target.value as string[])}
                  label="Speed"
                  renderValue={(selected) => `${selected.length} selected`}
                  sx={{
                    fontSize: 11,
                    height: 32,
                    bgcolor: 'rgba(255,255,255,0.03)',
                    color: 'text.primary',
                    '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.1)' },
                  }}
                >
                  {ALL_SPEEDS.map((speed) => (
                    <MenuItem key={speed} value={speed} sx={{ fontSize: 11 }}>
                      <Chip
                        label={t(`lichessFilters.speeds.${speed}`)}
                        size="small"
                        sx={{
                          height: 18,
                          fontSize: 9,
                          bgcolor: playerSpeeds.includes(speed) ? '#14b8a6' : 'rgba(255,255,255,0.08)',
                          color: playerSpeeds.includes(speed) ? '#fff' : 'text.secondary',
                        }}
                      />
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              {/* Mode selector */}
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

              {/* Recent games count */}
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
          )}

          {/* Player loading state */}
          {playerLoading && searchUsername && (
            <LinearProgress
              sx={{
                height: 2,
                '& .MuiLinearProgress-bar': { bgcolor: '#14b8a6' },
                bgcolor: 'rgba(20, 184, 166, 0.1)',
              }}
            />
          )}

          {/* Player upstream down warning */}
          {playerUpstreamDown && !playerLoading && !playerError && searchUsername && (
            <Box sx={{ py: 1, px: 1.5, bgcolor: 'rgba(251, 191, 36, 0.1)', borderRadius: 1, border: '1px solid rgba(251, 191, 36, 0.4)' }}>
              <Typography variant="caption" sx={{ color: '#f59e0b', fontSize: 11, display: 'block' }}>
                ⚠️ Lichess Explorer is currently unavailable. Showing cached data if available.
              </Typography>
            </Box>
          )}

          {/* Player error state */}
          {playerError && !playerLoading && searchUsername && (
            <Box sx={{ py: 1, px: 1.5, bgcolor: 'rgba(239, 68, 68, 0.1)', borderRadius: 1, border: '1px solid rgba(239, 68, 68, 0.3)' }}>
              <Typography variant="caption" sx={{ color: '#ef4444', fontSize: 11, display: 'block', mb: 0.5 }}>
                Failed to load player data
              </Typography>
              <Button
                size="small"
                startIcon={<Refresh sx={{ fontSize: 14 }} />}
                onClick={retryPlayer}
                sx={{ fontSize: 10, textTransform: 'none', color: '#ef4444', minHeight: 0, py: 0.3 }}
              >
                Retry
              </Button>
            </Box>
          )}

          {/* Player results - only show when username is searched */}
          {searchUsername && playerData && (
            <>
              {/* Player game count badge */}
              {playerTotalGames > 0 && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, fontSize: 11 }}>
                    {searchUsername} as {playerColor === 'white' ? t('lichessPlayer.white') : t('lichessPlayer.black')}
                  </Typography>
                  <Chip
                    label={`${playerTotalGames.toLocaleString()} games`}
                    size="small"
                    sx={{ height: 20, fontSize: 11, bgcolor: '#1f2937', color: '#fff' }}
                  />
                </Box>
              )}

              {/* Player move stats */}
              {!playerLoading && !playerError && playerData && (
                renderMoveStats(playerData, playerLoading, false)
              )}

              {/* Player games list */}
              {!playerLoading && !playerError && playerGames.length > 0 && (
                renderGamesList(playerGames, playerGamesPage, totalPlayerPages, setPlayerGamesPage, playerLoading)
              )}

              {/* Empty state - no player games found */}
              {!playerLoading && !playerError && playerTotalGames === 0 && (
                <EmptyState type="no-games" message={`No games found for ${searchUsername}`} />
              )}
            </>
          )}
        </>
      )}
    </Box>
  );
}
