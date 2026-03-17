/**
 * ChessComExplorerTab — Chess.com player search with progressive loading
 */

'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  Box,
  Typography,
  LinearProgress,
  Button,
  TextField,
  List,
  ListItem,
  ListItemText,
  Chip,
  IconButton,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
} from '@mui/material';
import { ChevronLeft, ChevronRight, Refresh, Search } from '@mui/icons-material';
import { useChessComExplorer } from '@/hooks/useChessComExplorer';
import type { GameSearchResult } from '@/hooks/useOpeningRepertoire';

interface ChessComExplorerTabProps {
  onOpenGame?: (game: GameSearchResult) => void;
}

const GAMES_PER_PAGE = 10;

export default function ChessComExplorerTab({
  onOpenGame,
}: ChessComExplorerTabProps) {
  const t = useTranslations('debut');
  const [username, setUsername] = useState('');
  const [searchUsername, setSearchUsername] = useState('');
  const [gamesPage, setGamesPage] = useState(0);

  // Filters
  const [timeControl, setTimeControl] = useState<string>('all');
  const [minRating, setMinRating] = useState<string>('');

  const { games, loading, error, retry, progress } = useChessComExplorer({
    username: searchUsername,
    enabled: !!searchUsername,
  });

  // Reset page when username or filters change
  useEffect(() => {
    setGamesPage(0);
  }, [searchUsername, timeControl, minRating]);

  // Client-side filtering
  const filteredGames = useMemo(() => {
    let filtered = games;

    // Filter by time control
    if (timeControl !== 'all') {
      filtered = filtered.filter((g) => {
        const event = g.event?.toLowerCase() || '';
        return event === timeControl;
      });
    }

    // Filter by min rating
    if (minRating) {
      const minRatingNum = parseInt(minRating, 10);
      if (!isNaN(minRatingNum)) {
        filtered = filtered.filter((g) => {
          const maxRating = Math.max(g.white_elo || 0, g.black_elo || 0);
          return maxRating >= minRatingNum;
        });
      }
    }

    return filtered;
  }, [games, timeControl, minRating]);

  const visibleGames = filteredGames.slice(gamesPage * GAMES_PER_PAGE, (gamesPage + 1) * GAMES_PER_PAGE);
  const totalPages = Math.ceil(filteredGames.length / GAMES_PER_PAGE);

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

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, py: 1 }}>
      {/* Username search */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <TextField
          size="small"
          placeholder="Chess.com username"
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
          Search
        </Button>
      </Box>

      {/* Filters */}
      {searchUsername && !error && (
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <FormControl size="small" sx={{ minWidth: 100 }}>
            <InputLabel sx={{ fontSize: 11, color: 'text.secondary' }}>Time Control</InputLabel>
            <Select
              value={timeControl}
              onChange={(e) => setTimeControl(e.target.value)}
              label="Time Control"
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
              <MenuItem value="all" sx={{ fontSize: 11 }}>All</MenuItem>
              <MenuItem value="bullet" sx={{ fontSize: 11 }}>Bullet</MenuItem>
              <MenuItem value="blitz" sx={{ fontSize: 11 }}>Blitz</MenuItem>
              <MenuItem value="rapid" sx={{ fontSize: 11 }}>Rapid</MenuItem>
              <MenuItem value="classical" sx={{ fontSize: 11 }}>Classical</MenuItem>
            </Select>
          </FormControl>

          <TextField
            size="small"
            type="number"
            placeholder="Min rating"
            value={minRating}
            onChange={(e) => setMinRating(e.target.value)}
            sx={{
              width: 100,
              '& .MuiInputBase-root': {
                fontSize: 11,
                height: 32,
                bgcolor: 'rgba(255,255,255,0.03)',
                color: 'text.primary',
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

          {filteredGames.length > 0 && (
            <Chip
              label={`${filteredGames.length} games`}
              size="small"
              sx={{ height: 20, fontSize: 11, bgcolor: '#1f2937', color: '#fff', ml: 'auto' }}
            />
          )}
        </Box>
      )}

      {/* Loading state with progress */}
      {loading && (
        <Box>
          <LinearProgress
            sx={{
              height: 2,
              '& .MuiLinearProgress-bar': { bgcolor: '#14b8a6' },
              bgcolor: 'rgba(20, 184, 166, 0.1)',
            }}
          />
          {progress && progress.total > 0 && (
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 10, mt: 0.5, display: 'block' }}>
              Loading archives... {progress.loaded} of {progress.total} months
            </Typography>
          )}
        </Box>
      )}

      {/* Error state */}
      {error && !loading && (
        <Box sx={{ py: 1, px: 1.5, bgcolor: 'rgba(239, 68, 68, 0.1)', borderRadius: 1, border: '1px solid rgba(239, 68, 68, 0.3)' }}>
          <Typography variant="caption" sx={{ color: '#ef4444', fontSize: 11, display: 'block', mb: 0.5 }}>
            {error}
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

      {/* Games list */}
      {!loading && !error && filteredGames.length > 0 && (
        <Box>
          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textTransform: 'uppercase', fontSize: 11, mb: 0.5, display: 'block' }}>
            Games
          </Typography>
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
                      <Chip label={g.event || 'Unknown'} size="small" sx={{ height: 14, fontSize: 9, bgcolor: 'action.hover', color: 'text.secondary' }} />
                      <Typography component="span" sx={{ color: 'text.secondary', fontSize: 10 }}>
                        {g.date}
                      </Typography>
                    </Box>
                  }
                />
              </ListItem>
            ))}
          </List>

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

      {/* Empty state (no username entered) */}
      {!searchUsername && !loading && (
        <Box sx={{ py: 2, textAlign: 'center' }}>
          <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: 12, fontStyle: 'italic' }}>
            Position search not available for Chess.com
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: 11, mt: 0.5 }}>
            Enter a Chess.com username to search their games
          </Typography>
        </Box>
      )}

      {/* Empty state (no games found) */}
      {!loading && !error && searchUsername && filteredGames.length === 0 && games.length > 0 && (
        <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: 12, fontStyle: 'italic', py: 1 }}>
          No games match the selected filters
        </Typography>
      )}

      {!loading && !error && searchUsername && games.length === 0 && (
        <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: 12, fontStyle: 'italic', py: 1 }}>
          No games found for this player
        </Typography>
      )}
    </Box>
  );
}
