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
  IconButton,
  CircularProgress,
  InputAdornment,
  Pagination,
  Button,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
} from '@mui/material';
import {
  Search,
  Star,
  StarBorder,
  Delete,
  FolderOpen,
  Add,
  Edit,
} from '@mui/icons-material';
import { useTranslations } from 'next-intl';
import { useAuth } from '@clerk/nextjs';
import { apiFetch } from '@/lib/api';
import { useUserGames, type UserGame, type ListGamesFilters } from '@/hooks/useUserGames';
import AddGameModal from './AddGameModal';
import EditGameModal from './EditGameModal';
import ShareMyGameButton from './ShareMyGameButton';
import ShareMyGamesButton from './ShareMyGamesButton';

type ResultFilter = '' | '1-0' | '0-1' | '1/2-1/2';

const SHARED_PER_PAGE = 20;

interface SharedCollectionResponse {
  games: UserGame[];
  total: number;
  page: number;
  per_page: number;
  owner_name?: string | null;
}

interface MyGamesPanelProps {
  onOpenGame?: (game: UserGame) => void;
  boardPgn?: string;
  boardHasMoves?: boolean;
  onBoardReset?: () => void;
  /**
   * When set, the panel renders a READ-ONLY view of another user's shared
   * collection (opaque token from `/g/c/<token>`). All mutation UI is hidden
   * and games are fetched from the authed collection-share endpoints.
   */
  sharedToken?: string;
  /**
   * When set, the list is scoped to this database (collection) and new games
   * are filed under it. Omit for the default "all games" view.
   */
  databaseId?: string;
}

export default function MyGamesPanel({ onOpenGame, boardPgn, boardHasMoves, onBoardReset, sharedToken, databaseId }: MyGamesPanelProps) {
  const t = useTranslations('debut');
  const isShared = !!sharedToken;
  const { getToken } = useAuth();
  const {
    games,
    total,
    page,
    perPage,
    loading,
    error,
    fetchGames,
    createGame,
    updateGame,
    deleteGame,
    toggleFavorite,
  } = useUserGames();

  const [searchQuery, setSearchQuery] = useState('');
  const [resultFilter, setResultFilter] = useState<ResultFilter>('');
  const [favoriteFilter, setFavoriteFilter] = useState(false);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingGame, setEditingGame] = useState<UserGame | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  // ─── Shared read-only collection state (only used when `sharedToken` set) ───
  const [sharedGames, setSharedGames] = useState<UserGame[]>([]);
  const [sharedTotal, setSharedTotal] = useState(0);
  const [sharedPage, setSharedPage] = useState(1);
  const [sharedOwner, setSharedOwner] = useState('');
  const [sharedLoading, setSharedLoading] = useState(false);
  const [sharedError, setSharedError] = useState<string | null>(null);
  const [sharedUnavailable, setSharedUnavailable] = useState(false);

  const buildFilters = useCallback((): ListGamesFilters => {
    const filters: ListGamesFilters = {};
    if (searchQuery.trim()) filters.q = searchQuery.trim();
    if (resultFilter) filters.result = resultFilter;
    if (favoriteFilter) filters.favorite = true;
    if (databaseId) filters.database_id = databaseId;
    return filters;
  }, [searchQuery, resultFilter, favoriteFilter, databaseId]);

  // Fetch one page of the shared collection from the authed endpoint.
  const fetchSharedCollection = useCallback(async (pageNum: number) => {
    if (!sharedToken) return;
    setSharedLoading(true);
    setSharedError(null);
    setSharedUnavailable(false);
    try {
      const clerkToken = await getToken();
      if (!clerkToken) throw Object.assign(new Error('Not authenticated'), { status: 401 });
      const apiBase = process.env.NEXT_PUBLIC_API_URL || '';
      const params = new URLSearchParams({ page: String(pageNum), per_page: String(SHARED_PER_PAGE) });
      const data = await apiFetch<SharedCollectionResponse>(
        `${apiBase}/api/games/collection/shared/${encodeURIComponent(sharedToken)}?${params}`,
        { headers: { Authorization: `Bearer ${clerkToken}` } },
      );
      setSharedGames(data.games);
      setSharedTotal(data.total);
      setSharedPage(data.page);
      setSharedOwner(data.owner_name ?? '');
    } catch (e: unknown) {
      const status = (e as { status?: number })?.status;
      if (status === 404) {
        // Unknown/revoked token.
        setSharedUnavailable(true);
      } else {
        setSharedError(e instanceof Error ? e.message : 'Failed to load collection');
      }
    } finally {
      setSharedLoading(false);
    }
  }, [sharedToken, getToken]);

  // Initial load (owner mode only — shared mode loads via its own effect)
  useEffect(() => {
    if (isShared) return;
    fetchGames(1, perPage, buildFilters());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Debounced search (owner mode only)
  useEffect(() => {
    if (isShared) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchGames(1, perPage, buildFilters());
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [isShared, searchQuery, resultFilter, favoriteFilter, fetchGames, perPage, buildFilters]);

  // Shared collection load (shared mode only)
  useEffect(() => {
    if (!isShared) return;
    fetchSharedCollection(1);
  }, [isShared, fetchSharedCollection]);

  const handlePageChange = (_: React.ChangeEvent<unknown>, newPage: number) => {
    if (isShared) {
      fetchSharedCollection(newPage);
      return;
    }
    fetchGames(newPage, perPage, buildFilters());
  };

  // Row click: in shared mode, fetch the single game through the collection-share
  // endpoint (notes stripped) before opening; otherwise open the owned game.
  const handleRowClick = useCallback(async (game: UserGame) => {
    if (!isShared) {
      onOpenGame?.(game);
      return;
    }
    try {
      const clerkToken = await getToken();
      if (!clerkToken) return;
      const apiBase = process.env.NEXT_PUBLIC_API_URL || '';
      const full = await apiFetch<UserGame>(
        `${apiBase}/api/games/collection/shared/${encodeURIComponent(sharedToken!)}/games/${encodeURIComponent(game.id)}`,
        { headers: { Authorization: `Bearer ${clerkToken}` } },
      );
      onOpenGame?.(full);
    } catch {
      // The list row already carries the full PGN — open it as a fallback.
      onOpenGame?.(game);
    }
  }, [isShared, sharedToken, getToken, onOpenGame]);

  const handleDelete = async (e: React.MouseEvent, gameId: string) => {
    e.stopPropagation();
    if (!confirm(t('myGames.confirmDelete'))) return;
    await deleteGame(gameId);
  };

  const handleToggleFavorite = async (e: React.MouseEvent, gameId: string) => {
    e.stopPropagation();
    await toggleFavorite(gameId);
  };

  const handleEditGame = useCallback((e: React.MouseEvent, game: UserGame) => {
    e.stopPropagation();
    setEditingGame(game);
    setEditModalOpen(true);
  }, []);

  const handleSaveGame = useCallback(async (
    pgn: string,
    metadata?: Parameters<typeof createGame>[1]
  ) => {
    // File the new game under the active database when one is selected.
    const withDb = databaseId ? { ...metadata, database_id: databaseId } : metadata;
    const game = await createGame(pgn, withDb);
    return game !== null;
  }, [createGame, databaseId]);

  // Unified view model — sourced from the shared endpoint in shared mode, from
  // the owned-games hook otherwise.
  const displayGames = isShared ? sharedGames : games;
  const displayTotal = isShared ? sharedTotal : total;
  const displayPage = isShared ? sharedPage : page;
  const displayPerPage = isShared ? SHARED_PER_PAGE : perPage;
  const displayLoading = isShared ? sharedLoading : loading;
  const displayError = isShared ? sharedError : error;
  const totalPages = Math.ceil(displayTotal / displayPerPage);

  const resultFilters: { value: ResultFilter; label: string }[] = [
    { value: '', label: t('myGames.filterAll') },
    { value: '1-0', label: '1-0' },
    { value: '0-1', label: '0-1' },
    { value: '1/2-1/2', label: '½-½' },
  ];

  // Revoked / unknown token — the whole collection is gone.
  if (isShared && sharedUnavailable) {
    return (
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
          {t('myGames.sharedUnavailable')}
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, p: 1 }}>
      {/* Owner mode: mutation UI (add/import + modals). Hidden in shared mode. */}
      {!isShared && (
        <>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            <Button
              variant="contained"
              size="small"
              startIcon={<Add />}
              onClick={() => setAddModalOpen(true)}
              sx={{
                fontSize: 12,
                textTransform: 'none',
                py: 0.75,
                flex: 1,
                background: 'linear-gradient(135deg, #7c3aed, #6366f1)',
                '&:hover': { background: 'linear-gradient(135deg, #6d28d9, #4f46e5)' },
              }}
            >
              {t('myGames.addGame')}
            </Button>
            <ShareMyGamesButton />
          </Box>

          <AddGameModal
            open={addModalOpen}
            onClose={() => setAddModalOpen(false)}
            onSave={handleSaveGame}
            boardPgn={boardPgn}
            boardHasMoves={boardHasMoves}
            onBoardReset={onBoardReset}
          />

          <EditGameModal
            open={editModalOpen}
            onClose={() => { setEditModalOpen(false); setEditingGame(null); }}
            game={editingGame}
            onSave={updateGame}
          />
        </>
      )}

      {/* Shared mode: owner header */}
      {isShared && sharedOwner && (
        <Typography variant="subtitle2" sx={{ fontSize: 14, fontWeight: 700, color: 'text.primary' }}>
          {t('myGames.sharedHeader', { name: sharedOwner })}
        </Typography>
      )}

      {/* Search + filters — owner mode only (the shared endpoint is unfiltered) */}
      {!isShared && (
        <>
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
        </>
      )}

      {/* Error state */}
      {displayError && (
        <Typography variant="caption" sx={{ color: 'error.main', fontSize: 12 }}>
          {displayError}
        </Typography>
      )}

      {/* Loading */}
      {displayLoading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress size={28} />
        </Box>
      )}

      {/* Empty state */}
      {!displayLoading && displayGames.length === 0 && (
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
            {isShared ? t('myGames.sharedEmpty') : t('myGames.noGames')}
          </Typography>
          {!isShared && (
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 11, opacity: 0.7, mt: 0.5 }}>
              {t('myGames.noGamesSubtitle')}
            </Typography>
          )}
        </Box>
      )}

      {/* Game table */}
      {!displayLoading && displayGames.length > 0 && (
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" sx={{ minWidth: 480 }}>
            <TableHead>
              <TableRow>
                <TableCell sx={thSx}></TableCell>
                <TableCell sx={thSx}>Year</TableCell>
                <TableCell sx={thSx}>White</TableCell>
                <TableCell sx={thSx}>Elo</TableCell>
                <TableCell sx={thSx}>Black</TableCell>
                <TableCell sx={thSx}>Elo</TableCell>
                <TableCell sx={thSx}>Result</TableCell>
                <TableCell sx={thSx}>ECO</TableCell>
                {!isShared && <TableCell sx={thSx}></TableCell>}
              </TableRow>
            </TableHead>
            <TableBody>
              {displayGames.map((game) => (
                <TableRow
                  key={game.id}
                  onClick={() => handleRowClick(game)}
                  sx={{
                    cursor: onOpenGame ? 'pointer' : 'default',
                    '&:hover': { bgcolor: 'rgba(255,255,255,0.06)' },
                    '&:hover .row-actions': { opacity: 1 },
                  }}
                >
                  {/* Favorite indicator */}
                  <TableCell sx={{ ...tdSx, width: 24, px: 0.5 }}>
                    {game.is_favorite && <Star sx={{ fontSize: 14, color: '#f59e0b' }} />}
                  </TableCell>
                  {/* Year */}
                  <TableCell sx={tdSx}>
                    {game.date ? game.date.substring(0, 4) : '—'}
                  </TableCell>
                  {/* White */}
                  <TableCell sx={{ ...tdSx, maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {game.white || '?'}
                  </TableCell>
                  {/* White Elo */}
                  <TableCell sx={{ ...tdSx, color: 'text.secondary' }}>
                    {game.white_elo ?? '—'}
                  </TableCell>
                  {/* Black */}
                  <TableCell sx={{ ...tdSx, maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {game.black || '?'}
                  </TableCell>
                  {/* Black Elo */}
                  <TableCell sx={{ ...tdSx, color: 'text.secondary' }}>
                    {game.black_elo ?? '—'}
                  </TableCell>
                  {/* Result */}
                  <TableCell sx={{
                    ...tdSx,
                    fontWeight: 600,
                    color: game.result === '1-0' ? '#4ade80' : game.result === '0-1' ? '#f87171' : '#9ca3af',
                  }}>
                    {game.result || '?'}
                  </TableCell>
                  {/* ECO */}
                  <TableCell sx={{ ...tdSx, color: 'text.secondary' }}>
                    {game.eco || ''}
                  </TableCell>
                  {/* Actions — owner mode only (hidden for shared read-only view) */}
                  {!isShared && (
                    <TableCell sx={{ ...tdSx, width: 90, px: 0.5 }}>
                      <Box
                        className="row-actions"
                        sx={{
                          display: 'flex',
                          gap: 0.25,
                          opacity: { xs: 1, md: 0 },
                          transition: 'opacity 0.15s',
                        }}
                      >
                        <IconButton
                          size="small"
                          onClick={(e) => handleToggleFavorite(e, game.id)}
                          sx={{ p: 0.5 }}
                          aria-label="toggle favorite"
                        >
                          {game.is_favorite
                            ? <Star sx={{ fontSize: 16, color: '#f59e0b' }} />
                            : <StarBorder sx={{ fontSize: 16, color: 'text.secondary' }} />
                          }
                        </IconButton>
                        <IconButton
                          size="small"
                          onClick={(e) => handleEditGame(e, game)}
                          sx={{ p: 0.5 }}
                          aria-label="edit game"
                        >
                          <Edit sx={{ fontSize: 14, color: 'text.secondary' }} />
                        </IconButton>
                        <ShareMyGameButton
                          gameId={game.id}
                          white={game.white}
                          black={game.black}
                        />
                        <IconButton
                          size="small"
                          onClick={(e) => handleDelete(e, game.id)}
                          sx={{ p: 0.5 }}
                          aria-label="delete game"
                        >
                          <Delete sx={{ fontSize: 14, color: 'text.secondary', '&:hover': { color: 'error.main' } }} />
                        </IconButton>
                      </Box>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <Box sx={{ display: 'flex', justifyContent: 'center', pt: 1 }}>
          <Pagination
            count={totalPages}
            page={displayPage}
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

// ─── Shared cell styles ───────────────────────────
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
