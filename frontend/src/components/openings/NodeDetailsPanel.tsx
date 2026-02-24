'use client';

import React, { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import {
  Box, Typography, Button, Chip, Divider, IconButton,
  List, ListItem, ListItemText,
  CircularProgress,
} from '@mui/material';
import {
  Storage, ChevronLeft, ChevronRight,
} from '@mui/icons-material';
import type { OpeningNode, GameLink, GameSearchResult } from '@/hooks/useOpeningRepertoire';
import MasterGamesFilter, { MasterGamesFilterState } from './MasterGamesFilter';

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
}

export default function NodeDetailsPanel({
  node, onUpdateNotes, onToggleCritical, onDeleteNode,
  onSearchGames, gameLinks, gameLinksLoading,
  masterGames = [], masterGamesTotal = 0, masterGamesLoading = false,
  onOpenGame,
  masterGamesFilters,
  onMasterGamesFilterChange,
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

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, p: 1.5, overflow: 'auto' }}>
      {/* Opening info */}
      {(node.opening_name || node.eco_code) && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          {node.eco_code && (
            <Chip label={node.eco_code} size="small" sx={{ bgcolor: 'primary.main', color: 'primary.contrastText', fontWeight: 600, fontSize: 12 }} />
          )}
          {node.opening_name && (
            <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 500 }}>
              {node.opening_name}
            </Typography>
          )}
        </Box>
      )}

      {/* Master Games (auto-fetched from TWIC) */}
      <Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
          <Storage sx={{ fontSize: 14, color: 'primary.light' }} />
          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textTransform: 'uppercase', fontSize: 11 }}>
            {t('masterGames')}
          </Typography>
          {masterGamesTotal > 0 && (
            <Chip
              label={masterGamesTotal.toLocaleString()}
              size="small"
              sx={{ height: 16, fontSize: 10, bgcolor: 'primary.dark', color: 'primary.contrastText', ml: 'auto' }}
            />
          )}
        </Box>

        {masterGamesFilters && onMasterGamesFilterChange && (
          <MasterGamesFilter
            filters={masterGamesFilters}
            onFilterChange={onMasterGamesFilterChange}
          />
        )}

        {masterGamesLoading ? (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 1 }}>
            <CircularProgress size={14} sx={{ color: 'primary.light' }} />
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>{t('searchingPosition')}</Typography>
          </Box>
        ) : masterGames.length > 0 ? (
          <Box>
            <List dense sx={{ p: 0 }}>
              {masterGames.slice(gamesPage * GAMES_PER_PAGE, (gamesPage + 1) * GAMES_PER_PAGE).map((g, idx) => (
                <ListItem
                  key={`master-${g.id || idx}`}
                  sx={{ px: 0, py: 0.3, cursor: onOpenGame ? 'pointer' : 'default', '&:hover': onOpenGame ? { bgcolor: 'rgba(255,255,255,0.04)' } : {} }}
                  onClick={() => onOpenGame?.(g)}
                >
                  <ListItemText
                    primary={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <Typography component="span" sx={{ color: 'text.primary', fontSize: 12 }}>
                          {g.white_name || g.white || '?'}
                        </Typography>
                        <Typography component="span" sx={{ color: 'text.secondary', fontSize: 10 }}>
                          ({g.white_elo || '?'})
                        </Typography>
                        <Typography component="span" sx={{ color: 'text.secondary', fontSize: 11 }}>{t('vs')}</Typography>
                        <Typography component="span" sx={{ color: 'text.primary', fontSize: 12 }}>
                          {g.black_name || g.black || '?'}
                        </Typography>
                        <Typography component="span" sx={{ color: 'text.secondary', fontSize: 10 }}>
                          ({g.black_elo || '?'})
                        </Typography>
                      </Box>
                    }
                    secondary={
                      <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', mt: 0.2 }}>
                        <Chip label={g.result || '?'} size="small" sx={{ height: 14, fontSize: 9, bgcolor: 'action.hover', color: 'text.secondary' }} />
                        {g.eco && <Chip label={g.eco} size="small" sx={{ height: 14, fontSize: 9, bgcolor: 'primary.dark', color: 'primary.contrastText' }} />}
                        {(g.date || g.year) && (
                          <Typography component="span" sx={{ color: 'text.secondary', fontSize: 10 }}>
                            {g.date || g.year}
                          </Typography>
                        )}
                      </Box>
                    }
                  />
                </ListItem>
              ))}
            </List>

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
                sx={{ color: 'primary.light', fontSize: 11, textTransform: 'none', mt: 0.5 }}
              >
                {t('viewAllGames', { count: masterGamesTotal.toLocaleString() })}
              </Button>
            )}
          </Box>
        ) : (
          <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: 12, fontStyle: 'italic' }}>
            {t('noMasterGames')}
          </Typography>
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
}
