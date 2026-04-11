/**
 * MyGamesPanel — Displays user's saved games with search, filters, and pagination
 */

'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  Box,
  Typography,
  TextField,
  Chip,
  Card,
  CardContent,
  IconButton,
  CircularProgress,
  InputAdornment,
  Pagination,
  Button,
} from '@mui/material';
import {
  Search,
  Star,
  StarBorder,
  Delete,
  FolderOpen,
  Add,
} from '@mui/icons-material';
import { useTranslations } from 'next-intl';
import { useUserGames, type UserGame, type ListGamesFilters } from '@/hooks/useUserGames';
import AddGameModal from './AddGameModal';

type ResultFilter = '' | '1-0' | '0-1' | '1/2-1/2';

interface MyGamesPanelProps {
  onOpenGame?: (game: UserGame) => void;
}

export default function MyGamesPanel({ onOpenGame }: MyGamesPanelProps) {
  const t = useTranslations('debut');
  const {
    games,
    total,
    page,
    perPage,
    loading,
    error,
    fetchGames,
    createGame,
    deleteGame,
    toggleFavorite,
  } = useUserGames();

  const [searchQuery, setSearchQuery] = useState('');
  const [resultFilter, setResultFilter] = useState<ResultFilter>('');
  const [favoriteFilter, setFavoriteFilter] = useState(false);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const buildFilters = useCallback((): ListGamesFilters => {
    const filters: ListGamesFilters = {};
    if (searchQuery.trim()) filters.q = searchQuery.trim();
    if (resultFilter) filters.result = resultFilter;
    if (favoriteFilter) filters.favorite = true;
    return filters;
  }, [searchQuery, resultFilter, favoriteFilter]);

  // Initial load
  useEffect(() => {
    fetchGames(1, perPage, buildFilters());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Debounced search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchGames(1, perPage, buildFilters());
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [searchQuery, resultFilter, favoriteFilter, fetchGames, perPage, buildFilters]);

  const handlePageChange = (_: React.ChangeEvent<unknown>, newPage: number) => {
    fetchGames(newPage, perPage, buildFilters());
  };

  const handleDelete = async (e: React.MouseEvent, gameId: string) => {
    e.stopPropagation();
    if (!confirm(t('myGames.confirmDelete'))) return;
    await deleteGame(gameId);
  };

  const handleToggleFavorite = async (e: React.MouseEvent, gameId: string) => {
    e.stopPropagation();
    await toggleFavorite(gameId);
  };

  const handleSaveGame = useCallback(async (
    pgn: string,
    metadata?: Parameters<typeof createGame>[1]
  ) => {
    const game = await createGame(pgn, metadata);
    return game !== null;
  }, [createGame]);

  const totalPages = Math.ceil(total / perPage);

  const resultFilters: { value: ResultFilter; label: string }[] = [
    { value: '', label: t('myGames.filterAll') },
    { value: '1-0', label: '1-0' },
    { value: '0-1', label: '0-1' },
    { value: '1/2-1/2', label: '½-½' },
  ];

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, p: 1 }}>
      {/* Add Game button */}
      <Button
        variant="contained"
        size="small"
        startIcon={<Add />}
        onClick={() => setAddModalOpen(true)}
        sx={{
          fontSize: 12,
          textTransform: 'none',
          py: 0.75,
          background: 'linear-gradient(135deg, #7c3aed, #6366f1)',
          '&:hover': { background: 'linear-gradient(135deg, #6d28d9, #4f46e5)' },
        }}
      >
        {t('myGames.addGame')}
      </Button>

      <AddGameModal
        open={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        onSave={handleSaveGame}
      />

      {/* Search */}
      <TextField
        size="small"
        placeholder={t('myGames.searchPlaceholder')}
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        slotProps={{
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <Search sx={{ fontSize: 18, color: 'text.secondary' }} />
              </InputAdornment>
            ),
          },
        }}
        sx={{
          '& .MuiOutlinedInput-root': {
            fontSize: 13,
            bgcolor: 'rgba(255,255,255,0.03)',
          },
        }}
      />

      {/* Filter chips */}
      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
        {resultFilters.map((f) => (
          <Chip
            key={f.value}
            label={f.label}
            size="small"
            onClick={() => setResultFilter(f.value)}
            sx={{
              height: 24,
              fontSize: 11,
              fontWeight: resultFilter === f.value ? 700 : 400,
              bgcolor: resultFilter === f.value ? 'primary.main' : 'rgba(255,255,255,0.06)',
              color: resultFilter === f.value ? '#fff' : 'text.secondary',
              '&:hover': { bgcolor: resultFilter === f.value ? 'primary.dark' : 'rgba(255,255,255,0.1)' },
            }}
          />
        ))}
        <Chip
          icon={<Star sx={{ fontSize: 14 }} />}
          label={t('myGames.filterFavorites')}
          size="small"
          onClick={() => setFavoriteFilter(!favoriteFilter)}
          sx={{
            height: 24,
            fontSize: 11,
            fontWeight: favoriteFilter ? 700 : 400,
            bgcolor: favoriteFilter ? '#f59e0b' : 'rgba(255,255,255,0.06)',
            color: favoriteFilter ? '#000' : 'text.secondary',
            '& .MuiChip-icon': {
              color: favoriteFilter ? '#000' : 'text.secondary',
            },
            '&:hover': { bgcolor: favoriteFilter ? '#d97706' : 'rgba(255,255,255,0.1)' },
          }}
        />
      </Box>

      {/* Error state */}
      {error && (
        <Typography variant="caption" sx={{ color: 'error.main', fontSize: 12 }}>
          {error}
        </Typography>
      )}

      {/* Loading */}
      {loading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress size={28} />
        </Box>
      )}

      {/* Empty state */}
      {!loading && games.length === 0 && (
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            py: 6,
            px: 2,
            textAlign: 'center',
          }}
        >
          <FolderOpen sx={{ fontSize: 48, color: 'text.secondary', opacity: 0.3, mb: 1.5 }} />
          <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: 13, fontWeight: 500 }}>
            {t('myGames.noGames')}
          </Typography>
          <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 11, opacity: 0.7, mt: 0.5 }}>
            {t('myGames.noGamesSubtitle')}
          </Typography>
        </Box>
      )}

      {/* Game list */}
      {!loading && games.length > 0 && (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
          {games.map((game) => (
            <GameRow
              key={game.id}
              game={game}
              onClick={() => onOpenGame?.(game)}
              onToggleFavorite={handleToggleFavorite}
              onDelete={handleDelete}
            />
          ))}
        </Box>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <Box sx={{ display: 'flex', justifyContent: 'center', pt: 1 }}>
          <Pagination
            count={totalPages}
            page={page}
            onChange={handlePageChange}
            size="small"
            sx={{
              '& .MuiPaginationItem-root': { fontSize: 12 },
            }}
          />
        </Box>
      )}
    </Box>
  );
}

// ─── Game Row ───────────────────────────

interface GameRowProps {
  game: UserGame;
  onClick?: () => void;
  onToggleFavorite: (e: React.MouseEvent, id: string) => void;
  onDelete: (e: React.MouseEvent, id: string) => void;
}

function GameRow({ game, onClick, onToggleFavorite, onDelete }: GameRowProps) {
  const resultColor =
    game.result === '1-0' ? '#f0f0f0' :
    game.result === '0-1' ? '#333' :
    '#888';

  return (
    <Card
      sx={{
        bgcolor: 'rgba(255,255,255,0.03)',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'all 0.15s ease',
        '&:hover': onClick ? {
          bgcolor: 'rgba(255,255,255,0.06)',
          transform: 'translateY(-1px)',
          boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
        } : {},
        border: '1px solid rgba(255,255,255,0.08)',
      }}
      onClick={onClick}
    >
      <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
          {/* Players & meta */}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            {/* Title */}
            {game.title && (
              <Typography
                sx={{
                  color: 'text.primary',
                  fontSize: 12,
                  fontWeight: 600,
                  mb: 0.5,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {game.title}
              </Typography>
            )}

            {/* Players */}
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.25 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Box sx={{ width: 8, height: 8, bgcolor: '#f0f0f0', borderRadius: '50%', flexShrink: 0 }} />
                <Typography
                  component="span"
                  sx={{ color: 'text.primary', fontSize: 12, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                >
                  {game.white || '?'}
                </Typography>
                {game.white_elo && (
                  <Typography component="span" sx={{ color: 'text.secondary', fontSize: 10, flexShrink: 0 }}>
                    ({game.white_elo})
                  </Typography>
                )}
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Box sx={{ width: 8, height: 8, bgcolor: '#333', borderRadius: '50%', flexShrink: 0 }} />
                <Typography
                  component="span"
                  sx={{ color: 'text.primary', fontSize: 12, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                >
                  {game.black || '?'}
                </Typography>
                {game.black_elo && (
                  <Typography component="span" sx={{ color: 'text.secondary', fontSize: 10, flexShrink: 0 }}>
                    ({game.black_elo})
                  </Typography>
                )}
              </Box>
            </Box>

            {/* Meta chips */}
            <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', alignItems: 'center', mt: 0.5 }}>
              <Chip
                label={game.result || '?'}
                size="small"
                sx={{
                  height: 18,
                  fontSize: 10,
                  bgcolor: resultColor,
                  color: game.result === '0-1' ? '#fff' : '#000',
                  fontWeight: 600,
                }}
              />
              {game.eco && (
                <Chip label={game.eco} size="small" sx={{ height: 18, fontSize: 9, bgcolor: '#1f2937', color: '#fff' }} />
              )}
              {game.opening_name && (
                <Typography
                  component="span"
                  sx={{ color: 'text.secondary', fontSize: 10, fontStyle: 'italic', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                >
                  {game.opening_name}
                </Typography>
              )}
              {game.date && (
                <Typography component="span" sx={{ color: 'text.secondary', fontSize: 10, ml: 'auto' }}>
                  {game.date}
                </Typography>
              )}
            </Box>

            {/* Tags */}
            {game.tags.length > 0 && (
              <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
                {game.tags.map((tag) => (
                  <Chip
                    key={tag}
                    label={tag}
                    size="small"
                    sx={{ height: 16, fontSize: 8, bgcolor: '#6366f1', color: '#fff', fontWeight: 600 }}
                  />
                ))}
              </Box>
            )}
          </Box>

          {/* Actions */}
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0.25, flexShrink: 0 }}>
            <IconButton
              size="small"
              onClick={(e) => onToggleFavorite(e, game.id)}
              sx={{ p: 0.5 }}
              aria-label="toggle favorite"
            >
              {game.is_favorite
                ? <Star sx={{ fontSize: 18, color: '#f59e0b' }} />
                : <StarBorder sx={{ fontSize: 18, color: 'text.secondary' }} />
              }
            </IconButton>
            <IconButton
              size="small"
              onClick={(e) => onDelete(e, game.id)}
              sx={{ p: 0.5 }}
              aria-label="delete game"
            >
              <Delete sx={{ fontSize: 16, color: 'text.secondary', '&:hover': { color: 'error.main' } }} />
            </IconButton>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}
