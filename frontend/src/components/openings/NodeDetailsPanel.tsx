'use client';

import React, { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import {
  Box, Typography, Button, Chip, Divider, IconButton,
  List, ListItem, ListItemText,
  LinearProgress,
} from '@mui/material';
import {
  Storage, ChevronLeft, ChevronRight,
} from '@mui/icons-material';
import type { OpeningNode, GameLink, GameSearchResult } from '@/hooks/useOpeningRepertoire';
import MasterGamesFilter, { MasterGamesFilterState } from './MasterGamesFilter';
import ExplorerTabs, { ExplorerTab } from './ExplorerTabs';
import LichessExplorerTab from './LichessExplorerTab';
import ChessComExplorerTab from './ChessComExplorerTab';
import GameTable from './GameTable';
import EmptyState from './EmptyState';

interface NodeDetailsPanelProps {
  node: OpeningNode | null;
  onUpdateNotes: (nodeId: string, notes: string) => Promise<void>;
  onToggleCritical: (nodeId: string, isCritical: boolean) => Promise<void>;
  onDeleteNode: (nodeId: string) => Promise<void>;
  onSearchGames: (fen: string) => void;
  gameLinks: GameLink[];
  gameLinksLoading: boolean;
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

export default function NodeDetailsPanel({
  node, onUpdateNotes, onToggleCritical, onDeleteNode,
  onSearchGames, gameLinks, gameLinksLoading,
  masterGames = [], masterGamesTotal = 0, masterGamesLoading = false,
  onOpenGame,
  masterGamesFilters,
  onMasterGamesFilterChange,
  explorerTab = 'twic',
  onExplorerTabChange,
  lichessDatabase = 'masters',
  onLichessDatabaseChange,
}: NodeDetailsPanelProps) {
  const t = useTranslations('debut');
  const [gamesPage, setGamesPage] = useState(0);
  const GAMES_PER_PAGE = 10;

  // Reset page when node changes
  useEffect(() => {
    setGamesPage(0);
  }, [node?.id]);

  if (!node) {
    return (
      <Box sx={{ p: 2, color: 'text.secondary' }}>
        <Typography variant="body2">{t('selectMoveDetails')}</Typography>
      </Box>
    );
  }

  const isRoot = node.move_san === null;
  let moveDisplay = t('startingPosition');
  if (node.move_san) {
    moveDisplay = node.is_white_move
      ? `${node.move_number}. ${node.move_san}`
      : `${node.move_number}... ${node.move_san}`;
  }

  // TWIC tab content
  const twicContent = (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, pt: 1 }}>
      {/* Master Games (auto-fetched from TWIC) */}
      <Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
          <Storage sx={{ fontSize: 14, color: '#14b8a6' }} />
          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textTransform: 'uppercase', fontSize: 11 }}>
            {t('masterGames')}
          </Typography>
          {masterGamesTotal > 0 && (
            <Chip
              label={(masterGamesTotal ?? 0).toLocaleString()}
              size="small"
              sx={{ height: 16, fontSize: 10, bgcolor: '#1f2937', color: '#fff', ml: 'auto' }}
            />
          )}
        </Box>

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

            {masterGamesTotal > masterGames.length && (
              <Button
                size="small"
                onClick={() => onSearchGames(node!.fen)}
                sx={{ color: '#14b8a6', fontSize: 11, textTransform: 'none', mt: 0.5 }}
              >
                {t('viewAllGames', { count: (masterGamesTotal ?? 0).toLocaleString() })}
              </Button>
            )}
          </Box>
        ) : (
          <EmptyState type="no-games" message={t('noMasterGames')} />
        )}
      </Box>

      {/* Linked games */}
      {gameLinks.length > 0 && (
        <>
          <Divider sx={{ borderColor: 'divider' }} />
          <Box>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textTransform: 'uppercase', fontSize: 11, mb: 0.5, display: 'block' }}>
              Linked Games ({gameLinks.length})
            </Typography>
            <List dense sx={{ p: 0 }}>
              {gameLinks.map(g => (
                <ListItem key={g.id} sx={{ px: 0, py: 0.3 }}>
                  <ListItemText
                    primary={`${g.white_player || '?'} ${t('vs')} ${g.black_player || '?'}`}
                    secondary={`${g.result || ''} · ${g.date_played || ''}`}
                    primaryTypographyProps={{ sx: { color: 'text.secondary', fontSize: 12 } }}
                    secondaryTypographyProps={{ sx: { color: 'text.secondary', fontSize: 10 } }}
                  />
                  <Chip label={g.game_source} size="small" sx={{ height: 16, fontSize: 9, bgcolor: 'action.hover', color: 'text.secondary' }} />
                </ListItem>
              ))}
            </List>
          </Box>
        </>
      )}
    </Box>
  );

  // Lichess tab content
  const lichessContent = (
    <LichessExplorerTab
      fen={node.fen}
      database={lichessDatabase}
      onDatabaseChange={(db) => onLichessDatabaseChange?.(db)}
      onOpenGame={onOpenGame}
    />
  );

  // Chess.com tab content
  const chesscomContent = (
    <ChessComExplorerTab
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
