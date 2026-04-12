'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  Box, Typography, Chip, IconButton, Tooltip, CircularProgress, Button,
} from '@mui/material';
import { ChevronLeft, ChevronRight, FirstPage, LastPage, BookmarkBorder, Bookmark, Edit, Save } from '@mui/icons-material';
import { Chess } from 'chess.js';
import SourceBadge, { GameSource } from './SourceBadge';
import type { OpeningNode } from '@/hooks/useOpeningRepertoire';
import type { MoveContextMenuActions } from './MoveNotation';

export interface OpenedGame {
  id: string;
  white: string;
  black: string;
  whiteElo?: number;
  blackElo?: number;
  result: string;
  eco?: string;
  date?: string;
  event?: string;
  pgn: string;
  moves: string[];         // SAN moves parsed from PGN
  fens: string[];           // FEN at each move index (index 0 = after move 1)
  startingFen: string;
  source?: GameSource | string;
}

interface GameViewerPanelProps {
  game: OpenedGame;
  currentMoveIndex: number;  // -1 = starting position
  onMoveIndexChange: (index: number) => void;
  onSaveToMyGames?: (game: OpenedGame) => Promise<boolean>;
  isSaved?: boolean;
  onEditGame?: () => void;
  // Editing props (active for source===user only)
  isEditable?: boolean;
  editTree?: OpeningNode | null;
  editSelectedNodeId?: string | null;
  onEditNodeSelect?: (node: OpeningNode) => void;
  onEditSave?: () => void;
  editIsDirty?: boolean;
  editContextMenuActions?: MoveContextMenuActions;
}

export function parseGamePgn(pgn: string): { moves: string[]; fens: string[]; startingFen: string } {
  const chess = new Chess();
  try {
    chess.loadPgn(pgn);
  } catch {
    // If loadPgn fails, try extracting moves manually
    const moveText = pgn.replace(/\[.*?\]\s*/g, '').replace(/\{.*?\}/g, '').trim();
    const tokens = moveText.split(/\s+/).filter(t => !t.match(/^\d+\./) && !t.match(/^(1-0|0-1|1\/2-1\/2|\*)$/));
    const fresh = new Chess();
    const moves: string[] = [];
    const fens: string[] = [];
    for (const token of tokens) {
      try {
        fresh.move(token);
        moves.push(token);
        fens.push(fresh.fen());
      } catch { break; }
    }
    return { moves, fens, startingFen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1' };
  }

  const history = chess.history();
  // Replay to get FENs at each position
  const fens: string[] = [];
  const replay = new Chess();
  for (const move of history) {
    replay.move(move);
    fens.push(replay.fen());
  }

  return {
    moves: history,
    fens,
    startingFen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
  };
}

export default function GameViewerPanel({
  game, currentMoveIndex, onMoveIndexChange,
  onSaveToMyGames, isSaved = false, onEditGame,
  isEditable, editTree, editSelectedNodeId, onEditNodeSelect, onEditSave, editIsDirty, editContextMenuActions,
}: GameViewerPanelProps) {
  const t = useTranslations('debut');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(isSaved);

  useEffect(() => { setSaved(isSaved); }, [isSaved]);

  const handleSave = useCallback(async () => {
    if (!onSaveToMyGames || saving || saved) return;
    setSaving(true);
    const success = await onSaveToMyGames(game);
    setSaving(false);
    if (success) setSaved(true);
  }, [onSaveToMyGames, saving, saved, game]);

  // Keyboard navigation (only for non-editable / flat mode)
  useEffect(() => {
    if (isEditable && editTree) return; // Tree mode handles its own nav
    const handleKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      switch (e.key) {
        case 'ArrowLeft': e.preventDefault(); onMoveIndexChange(Math.max(-1, currentMoveIndex - 1)); break;
        case 'ArrowRight': e.preventDefault(); onMoveIndexChange(Math.min(game.moves.length - 1, currentMoveIndex + 1)); break;
        case 'Home': e.preventDefault(); onMoveIndexChange(-1); break;
        case 'End': e.preventDefault(); onMoveIndexChange(game.moves.length - 1); break;
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [currentMoveIndex, game.moves.length, onMoveIndexChange, isEditable, editTree]);

  // Build move pairs for display (1. e4 e5  2. Nf3 Nc6 ...)
  const movePairs = useMemo(() => {
    const pairs: { num: number; white: { san: string; idx: number }; black?: { san: string; idx: number } }[] = [];
    for (let i = 0; i < game.moves.length; i += 2) {
      pairs.push({
        num: Math.floor(i / 2) + 1,
        white: { san: game.moves[i], idx: i },
        black: i + 1 < game.moves.length ? { san: game.moves[i + 1], idx: i + 1 } : undefined,
      });
    }
    return pairs;
  }, [game.moves]);

  // Use tree-based notation when editing
  const useTreeMode = isEditable && editTree && onEditNodeSelect;

  // Lazy-load MoveNotation only when needed
  const MoveNotation = useMemo(() => {
    if (!useTreeMode) return null;
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('./MoveNotation').default;
  }, [useTreeMode]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Game header */}
      <Box sx={{ p: 1.5, borderBottom: 1, borderColor: 'divider' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <Typography variant="body2" sx={{ color: 'text.primary', fontWeight: 600, fontSize: 13, flex: 1, minWidth: 0 }}>
            {game.white} {game.whiteElo ? `(${game.whiteElo})` : ''} {t('vs')} {game.black} {game.blackElo ? `(${game.blackElo})` : ''}
          </Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
            {onEditGame && (
              <Tooltip title={t('myGames.editModal.title')}>
                <IconButton
                  size="small"
                  onClick={onEditGame}
                  aria-label="edit game"
                  sx={{ p: 0.5, ml: 0.5 }}
                >
                  <Edit sx={{ fontSize: 18, color: 'text.secondary' }} />
                </IconButton>
              </Tooltip>
            )}
            {onSaveToMyGames && (
              <Tooltip title={saved ? t('savedToMyGames') : t('saveToMyGames')}>
                <span>
                  <IconButton
                    size="small"
                    onClick={handleSave}
                    disabled={saving || saved}
                    aria-label={saved ? t('savedToMyGames') : t('saveToMyGames')}
                    sx={{ p: 0.5, ml: 0.5 }}
                  >
                    {saving ? (
                      <CircularProgress size={16} />
                    ) : saved ? (
                      <Bookmark sx={{ fontSize: 18, color: 'primary.main' }} />
                    ) : (
                      <BookmarkBorder sx={{ fontSize: 18, color: 'text.secondary' }} />
                    )}
                  </IconButton>
                </span>
              </Tooltip>
            )}
          </Box>
        </Box>
        <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', mt: 0.5 }}>
          {game.source && <SourceBadge source={game.source} />}
          <Chip label={game.result} size="small" sx={{ height: 18, fontSize: 10, bgcolor: 'divider', color: 'text.secondary' }} />
          {game.eco && <Chip label={game.eco} size="small" sx={{ height: 18, fontSize: 10, bgcolor: 'primary.dark', color: 'primary.contrastText' }} />}
          {game.date && <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: 10 }}>{game.date}</Typography>}
          {game.event && <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: 10, ml: 0.5 }}>· {game.event}</Typography>}
        </Box>
      </Box>

      {/* Move list — tree mode (editable) or flat mode */}
      <Box sx={{ flex: 1, overflow: 'auto', p: useTreeMode ? 0 : 1 }}>
        {useTreeMode && MoveNotation ? (
          <MoveNotation
            tree={editTree}
            selectedNodeId={editSelectedNodeId || null}
            onNodeSelect={onEditNodeSelect}
            loading={false}
            contextMenuActions={editContextMenuActions}
          />
        ) : (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.3, alignItems: 'baseline' }}>
            {movePairs.map(pair => (
              <Box key={pair.num} sx={{ display: 'inline-flex', alignItems: 'baseline', gap: 0.3 }}>
                <Typography component="span" sx={{ color: 'text.disabled', fontSize: 12, minWidth: 20, textAlign: 'right', mr: 0.2 }}>
                  {pair.num}.
                </Typography>
                <Typography
                  component="span"
                  onClick={() => onMoveIndexChange(pair.white.idx)}
                  sx={{
                    fontSize: 13,
                    fontFamily: 'monospace',
                    cursor: 'pointer',
                    px: 0.4,
                    py: 0.1,
                    borderRadius: 0.5,
                    color: currentMoveIndex === pair.white.idx ? 'primary.contrastText' : 'text.secondary',
                    bgcolor: currentMoveIndex === pair.white.idx ? 'primary.main' : 'transparent',
                    '&:hover': { bgcolor: currentMoveIndex === pair.white.idx ? 'primary.main' : 'action.hover' },
                  }}
                >
                  {pair.white.san}
                </Typography>
                {pair.black && (
                  <Typography
                    component="span"
                    onClick={() => onMoveIndexChange(pair.black!.idx)}
                    sx={{
                      fontSize: 13,
                      fontFamily: 'monospace',
                      cursor: 'pointer',
                      px: 0.4,
                      py: 0.1,
                      borderRadius: 0.5,
                      color: currentMoveIndex === pair.black.idx ? 'primary.contrastText' : 'text.secondary',
                      bgcolor: currentMoveIndex === pair.black.idx ? 'primary.main' : 'transparent',
                      '&:hover': { bgcolor: currentMoveIndex === pair.black.idx ? 'primary.main' : 'action.hover' },
                      mr: 0.5,
                    }}
                  >
                    {pair.black.san}
                  </Typography>
                )}
              </Box>
            ))}
            {game.result && game.result !== '*' && (
              <Typography component="span" sx={{ color: 'text.disabled', fontSize: 12, fontWeight: 600, ml: 0.5 }}>
                {game.result}
              </Typography>
            )}
          </Box>
        )}
      </Box>

      {/* Save button (only shown when editable and dirty) */}
      {isEditable && editIsDirty && onEditSave && (
        <Box sx={{ px: 1.5, py: 1, borderTop: 1, borderColor: 'divider' }}>
          <Button
            variant="contained"
            size="small"
            startIcon={<Save sx={{ fontSize: 16 }} />}
            onClick={onEditSave}
            fullWidth
            sx={{
              textTransform: 'none',
              fontSize: 12,
              fontWeight: 600,
              background: 'linear-gradient(135deg, #7c3aed, #6d28d9)',
              '&:hover': { background: 'linear-gradient(135deg, #6d28d9, #5b21b6)' },
            }}
          >
            {t('myGames.moveEdit.saveChanges')}
          </Button>
        </Box>
      )}

      {/* Unsaved indicator */}
      {isEditable && editIsDirty && (
        <Typography
          variant="caption"
          sx={{ textAlign: 'center', color: 'warning.main', fontSize: 10, pb: 0.5 }}
        >
          {t('myGames.moveEdit.unsavedChanges')}
        </Typography>
      )}

      {/* Navigation controls (only for flat mode) */}
      {!useTreeMode && (
        <Box sx={{ display: 'flex', justifyContent: 'center', gap: 0.5, p: 0.5, borderTop: 1, borderColor: 'divider' }}>
          <Tooltip title={t('navStart')}>
            <IconButton size="small" onClick={() => onMoveIndexChange(-1)} disabled={currentMoveIndex === -1} sx={{ color: 'text.secondary' }}>
              <FirstPage fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title={t('navPrevious')}>
            <IconButton size="small" onClick={() => onMoveIndexChange(Math.max(-1, currentMoveIndex - 1))} disabled={currentMoveIndex === -1} sx={{ color: 'text.secondary' }}>
              <ChevronLeft fontSize="small" />
            </IconButton>
          </Tooltip>
          <Typography variant="caption" sx={{ color: 'text.disabled', alignSelf: 'center', minWidth: 50, textAlign: 'center' }}>
            {currentMoveIndex + 1} / {game.moves.length}
          </Typography>
          <Tooltip title={t('navNext')}>
            <IconButton size="small" onClick={() => onMoveIndexChange(Math.min(game.moves.length - 1, currentMoveIndex + 1))} disabled={currentMoveIndex >= game.moves.length - 1} sx={{ color: 'text.secondary' }}>
              <ChevronRight fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title={t('navEnd')}>
            <IconButton size="small" onClick={() => onMoveIndexChange(game.moves.length - 1)} disabled={currentMoveIndex >= game.moves.length - 1} sx={{ color: 'text.secondary' }}>
              <LastPage fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      )}
    </Box>
  );
}
