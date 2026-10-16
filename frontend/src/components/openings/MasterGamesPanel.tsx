'use client';

import React, { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import {
  Box, Typography, Chip, IconButton, LinearProgress,
} from '@mui/material';
import {
  Storage, ChevronLeft, ChevronRight,
} from '@mui/icons-material';
import type { GameSearchResult } from '@/hooks/useMasterGames';
import { apiFetch } from '@/lib/api';
import MasterGamesFilter, { MasterGamesFilterState } from './MasterGamesFilter';
import ExplorerTabs, { ExplorerTab } from './ExplorerTabs';
import LichessExplorerTab from './LichessExplorerTab';
import ChessComExplorerTab from './ChessComExplorerTab';
import GameTable from './GameTable';
import EmptyState from './EmptyState';

interface MasterGamesPanelProps {
  /** Board position the games and explorer tabs are shown for. */
  fen: string;
  masterGames?: GameSearchResult[];
  masterGamesTotal?: number;
  masterGamesLoading?: boolean;
  onOpenGame?: (game: any) => void;
  masterGamesFilters?: MasterGamesFilterState;
  onMasterGamesFilterChange?: (filters: MasterGamesFilterState) => void;
  explorerTab?: ExplorerTab;
  onExplorerTabChange?: (tab: ExplorerTab) => void;
  lichessDatabase?: 'masters' | 'lichess';
  onLichessDatabaseChange?: (db: 'masters' | 'lichess') => void;
}

export default function MasterGamesPanel({
  fen,
  masterGames = [], masterGamesTotal = 0, masterGamesLoading = false,
  onOpenGame,
  masterGamesFilters,
  onMasterGamesFilterChange,
  explorerTab = 'twic',
  onExplorerTabChange,
  lichessDatabase = 'masters',
  onLichessDatabaseChange,
}: MasterGamesPanelProps) {
  const t = useTranslations('debut');
  const [gamesPage, setGamesPage] = useState(0);
  const GAMES_PER_PAGE = 10;

  // Reset page when the position OR the active master-games filter set changes.
  // Otherwise paging to e.g. page 3 then typing a player name leaves gamesPage
  // stale, so the slice falls off the end of the (shorter) filtered list and
  // GameTable renders a blank cut-off list.
  useEffect(() => {
    setGamesPage(0);
  }, [fen, masterGamesFilters]);

  // Clamp the page so it can never exceed the last valid page for the current
  // result length (guards against the list shrinking under the current page).
  useEffect(() => {
    const lastPage = Math.max(0, Math.ceil(masterGames.length / GAMES_PER_PAGE) - 1);
    setGamesPage(p => Math.min(p, lastPage));
  }, [masterGames.length]);

  // Master DB global game count — mirrors the MasterDatabaseHero fetch in
  // /database so the panel shows "reach this position" vs the full DB total.
  const [masterDbGameCount, setMasterDbGameCount] = useState<number | null>(null);
  useEffect(() => {
    let cancelled = false;
    const apiBase = process.env.NEXT_PUBLIC_API_URL || '';
    apiFetch<{ game_count: number }>(`${apiBase}/api/opponent/status`)
      .then(data => { if (!cancelled) setMasterDbGameCount(data.game_count); })
      .catch(() => { /* silent: subtitle just hides */ });
    return () => { cancelled = true; };
  }, []);

  // TWIC tab content
  const twicContent = (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, pt: 1 }}>
      {/* Master Games (auto-fetched from TWIC) */}
      <Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.25 }}>
          <Storage sx={{ fontSize: 14, color: '#14b8a6' }} />
          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textTransform: 'uppercase', fontSize: 11 }}>
            {t('masterGames')}
          </Typography>
          {masterGamesTotal > 0 && (
            <Chip
              label={`${(masterGamesTotal ?? 0).toLocaleString()} games reach this position`}
              size="small"
              sx={{ height: 16, fontSize: 10, bgcolor: '#1f2937', color: '#fff', ml: 'auto' }}
            />
          )}
          {masterGamesFilters?.playerColor && onMasterGamesFilterChange && (
            <Chip
              label={`${masterGamesFilters.playerColor === 'white' ? '♔' : '♚'} ${masterGamesFilters.playerName?.trim() || t('colorFilterPlayer')} ${masterGamesFilters.playerColor === 'white' ? t('asWhite') : t('asBlack')}`}
              size="small"
              onDelete={() => onMasterGamesFilterChange({ ...masterGamesFilters, playerColor: '' })}
              sx={{
                height: 20,
                fontSize: 10,
                bgcolor: 'rgba(20,184,166,0.14)',
                color: '#14b8a6',
                border: '1px solid rgba(20,184,166,0.35)',
                ml: masterGamesTotal > 0 ? 0.5 : 'auto',
                '& .MuiChip-deleteIcon': { color: '#14b8a6', fontSize: 14, '&:hover': { color: '#0d9488' } },
              }}
            />
          )}
        </Box>
        {masterDbGameCount !== null && (
          <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 10, opacity: 0.7, display: 'block', mb: 0.5 }}>
            Master DB: {masterDbGameCount.toLocaleString()} games
          </Typography>
        )}

        {masterGamesFilters && onMasterGamesFilterChange && (
          <MasterGamesFilter
            filters={masterGamesFilters}
            onFilterChange={onMasterGamesFilterChange}
          />
        )}

        {masterGames.length > 0 || masterGamesLoading ? (
          <Box sx={{ position: 'relative' }}>
            {masterGamesLoading && (
              <LinearProgress sx={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, '& .MuiLinearProgress-bar': { bgcolor: '#14b8a6' }, bgcolor: 'transparent', zIndex: 1 }} />
            )}
            {masterGames.length === 0 && masterGamesLoading ? (
              <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 11, opacity: 0.5, py: 0.5, display: 'block' }}>
                {t('searchingPosition')}
              </Typography>
            ) : (
              <GameTable
                games={masterGames.slice(gamesPage * GAMES_PER_PAGE, (gamesPage + 1) * GAMES_PER_PAGE)}
                onOpenGame={onOpenGame}
                loading={masterGamesLoading}
              />
            )}

            {/* Pagination controls */}
            {masterGames.length > GAMES_PER_PAGE && (
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1, mt: 0.5 }}>
                <IconButton
                  size="small"
                  disabled={gamesPage === 0}
                  onClick={() => setGamesPage(p => p - 1)}
                  sx={{ color: 'text.secondary', p: 0.3 }}
                >
                  <ChevronLeft sx={{ fontSize: 18 }} />
                </IconButton>
                <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 11 }}>
                  {gamesPage + 1} / {Math.ceil(masterGames.length / GAMES_PER_PAGE)}
                </Typography>
                <IconButton
                  size="small"
                  disabled={(gamesPage + 1) * GAMES_PER_PAGE >= masterGames.length}
                  onClick={() => setGamesPage(p => p + 1)}
                  sx={{ color: 'text.secondary', p: 0.3 }}
                >
                  <ChevronRight sx={{ fontSize: 18 }} />
                </IconButton>
              </Box>
            )}
          </Box>
        ) : (
          <EmptyState type="no-games" message={t('noMasterGames')} />
        )}
      </Box>
    </Box>
  );

  // Lichess tab content
  const lichessContent = (
    <LichessExplorerTab
      fen={fen}
      database={lichessDatabase}
      onDatabaseChange={(db) => onLichessDatabaseChange?.(db)}
      onOpenGame={onOpenGame}
    />
  );

  // Chess.com tab content
  const chesscomContent = (
    <ChessComExplorerTab
      fen={fen}
      onOpenGame={onOpenGame}
    />
  );

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {onExplorerTabChange ? (
        <ExplorerTabs
          activeTab={explorerTab}
          onTabChange={onExplorerTabChange}
          twicContent={twicContent}
          lichessContent={lichessContent}
          chesscomContent={chesscomContent}
        />
      ) : (
        <Box sx={{ p: 1.5, overflow: 'auto' }}>{twicContent}</Box>
      )}
    </Box>
  );
}
