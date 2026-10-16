'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  Box, Typography, Chip, IconButton, Tooltip, CircularProgress, Button, TextField,
} from '@mui/material';
import { ChevronLeft, ChevronRight, FirstPage, LastPage, BookmarkBorder, Bookmark, Edit, Save, Star, StarBorder, Delete } from '@mui/icons-material';
import { Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions } from '@mui/material';
import { Chess } from 'chess.js';
import SourceBadge, { GameSource } from './SourceBadge';
import ShareGameButton from './ShareGameButton';
import type { OpeningNode } from '@/types/openingNode';
import type { MoveContextMenuActions, VoiceNotePlayback } from './MoveNotation';
import type { SaveStatus } from './useAutoSave';


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
  /** Unsaved "Add variation" board — Save creates a new game instead of updating. */
  isDraft?: boolean;
  /** Variation title (user games only); shown instead of the players header. */
  title?: string;
  /** Opened from a shared collection / database — never editable. */
  readOnly?: boolean;
  /** Share token of the shared database it came from (voice-note playback). */
  sharedDbToken?: string;
}

/** Saved variations are tagged event 'Variation'; drafts are variations until saved. */
export function isVariationGame(game: Pick<OpenedGame, 'event' | 'isDraft'>): boolean {
  return Boolean(game.isDraft) || game.event === 'Variation';
}

interface GameViewerPanelProps {
  game: OpenedGame;
  currentMoveIndex: number;  // -1 = starting position
  onMoveIndexChange: (index: number) => void;
  onSaveToMyGames?: (game: OpenedGame) => Promise<boolean>;
  isSaved?: boolean;
  onEditGame?: () => void;
  // Favorite/delete actions (for user games in viewer)
  onToggleFavorite?: () => void;
  onDeleteGame?: () => void;
  isFavorite?: boolean;
  // Editing props (active for source===user only)
  isEditable?: boolean;
  /** Move tree to show instead of the flat move list; editable only with isEditable. */
  editTree?: OpeningNode | null;
  editSelectedNodeId?: string | null;
  onEditNodeSelect?: (node: OpeningNode) => void;
  onEditSave?: () => void;
  editIsDirty?: boolean;
  /** Auto-save state of the edited tree, shown under the header. */
  saveStatus?: SaveStatus;
  onRetrySave?: () => void;
  editContextMenuActions?: MoveContextMenuActions;
  // Tree navigation (for keyboard support in tree mode)
  onTreePrev?: () => void;
  onTreeNext?: () => void;
  onTreeGoToStart?: () => void;
  onTreeGoToEnd?: () => void;
  /** Rename a variation; receives the trimmed title, or null when cleared. */
  onTitleChange?: (title: string | null) => void;
  voiceNotes?: VoiceNotePlayback;
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
  onToggleFavorite, onDeleteGame, isFavorite = false,
  isEditable, editTree, editSelectedNodeId, onEditNodeSelect, onEditSave, editIsDirty, saveStatus = 'idle', onRetrySave, editContextMenuActions,
  onTreePrev, onTreeNext, onTreeGoToStart, onTreeGoToEnd, onTitleChange, voiceNotes,
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

  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  const isVariation = isVariationGame(game);
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState('');

  useEffect(() => { setEditingTitle(false); }, [game.id]);

  const startTitleEdit = useCallback(() => {
    setTitleDraft(game.title ?? '');
    setEditingTitle(true);
  }, [game.title]);

  const commitTitle = useCallback(() => {
    setEditingTitle(false);
    const next = titleDraft.trim() || null;
    if (next !== (game.title || null)) onTitleChange?.(next);
  }, [titleDraft, game.title, onTitleChange]);

  const cancelTitleEdit = useCallback(() => {
    // Reset first so the blur fired on unmount commits nothing.
    setTitleDraft(game.title ?? '');
    setEditingTitle(false);
  }, [game.title]);

  const handleDeleteConfirm = useCallback(() => {
    setDeleteDialogOpen(false);
    onDeleteGame?.();
  }, [onDeleteGame]);

  // Keyboard navigation (flat mode + tree mode)
  useEffect(() => {
    const inTreeMode = !!editTree;
    const handleKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (inTreeMode) {
        switch (e.key) {
          case 'ArrowLeft': e.preventDefault(); onTreePrev?.(); break;
          case 'ArrowRight': e.preventDefault(); onTreeNext?.(); break;
          case 'Home': e.preventDefault(); onTreeGoToStart?.(); break;
          case 'End': e.preventDefault(); onTreeGoToEnd?.(); break;
        }
      } else {
        switch (e.key) {
          case 'ArrowLeft': e.preventDefault(); onMoveIndexChange(Math.max(-1, currentMoveIndex - 1)); break;
          case 'ArrowRight': e.preventDefault(); onMoveIndexChange(Math.min(game.moves.length - 1, currentMoveIndex + 1)); break;
          case 'Home': e.preventDefault(); onMoveIndexChange(-1); break;
          case 'End': e.preventDefault(); onMoveIndexChange(game.moves.length - 1); break;
        }
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [currentMoveIndex, game.moves.length, onMoveIndexChange, isEditable, editTree, onTreePrev, onTreeNext, onTreeGoToStart, onTreeGoToEnd]);

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
  const useTreeMode = !!editTree && !!onEditNodeSelect;

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
          {!isVariation ? (
            <Typography variant="body2" sx={{ color: 'text.primary', fontWeight: 600, fontSize: 13, flex: 1, minWidth: 0 }}>
              {game.white} {game.whiteElo ? `(${game.whiteElo})` : ''} {t('vs')} {game.black} {game.blackElo ? `(${game.blackElo})` : ''}
            </Typography>
          ) : editingTitle ? (
            <TextField
              value={titleDraft}
              onChange={(e) => setTitleDraft(e.target.value)}
              onBlur={commitTitle}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); commitTitle(); }
                else if (e.key === 'Escape') { e.preventDefault(); cancelTitleEdit(); }
              }}
              placeholder={t('myGames.titlePlaceholder')}
              autoFocus
              size="small"
              variant="standard"
              slotProps={{ htmlInput: { maxLength: 120, 'aria-label': t('myGames.titlePlaceholder') } }}
              sx={{ flex: 1, minWidth: 0, mr: 1, '& input': { fontSize: 13, fontWeight: 600, py: 0.25 } }}
            />
          ) : (
            <Box sx={{ display: 'flex', alignItems: 'center', flex: 1, minWidth: 0 }}>
              <Typography
                variant="body2"
                noWrap
                sx={{ color: game.title ? 'text.primary' : 'text.disabled', fontWeight: 600, fontSize: 13, minWidth: 0 }}
              >
                {game.title || t('myGames.untitledVariation')}
              </Typography>
              {onTitleChange && (
                <Tooltip title={t('myGames.editTitle')}>
                  <IconButton
                    size="small"
                    onClick={startTitleEdit}
                    aria-label={t('myGames.editTitle')}
                    sx={{ p: 0.5, ml: 0.5 }}
                  >
                    <Edit sx={{ fontSize: 16, color: 'text.secondary' }} />
                  </IconButton>
                </Tooltip>
              )}
            </Box>
          )}
          <Box sx={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
            <ShareGameButton
              source={game.source || 'twic'}
              gameId={game.id}
              white={game.white}
              black={game.black}
            />
            {onToggleFavorite && (
              <Tooltip title={isFavorite ? 'Unfavorite' : 'Favorite'}>
                <IconButton
                  size="small"
                  onClick={onToggleFavorite}
                  aria-label="toggle favorite"
                  sx={{ p: 0.5, ml: 0.5 }}
                >
                  {isFavorite
                    ? <Star sx={{ fontSize: 18, color: '#f59e0b' }} />
                    : <StarBorder sx={{ fontSize: 18, color: 'text.secondary' }} />
                  }
                </IconButton>
              </Tooltip>
            )}
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
            {onDeleteGame && (
              <Tooltip title="Delete game">
                <IconButton
                  size="small"
                  onClick={() => setDeleteDialogOpen(true)}
                  aria-label="delete game"
                  sx={{ p: 0.5, ml: 0.5 }}
                >
                  <Delete sx={{ fontSize: 18, color: 'text.secondary', '&:hover': { color: 'error.main' } }} />
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
        {!isVariation && (
          <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', mt: 0.5 }}>
            {game.source && <SourceBadge source={game.source} />}
            <Chip label={game.result} size="small" sx={{ height: 18, fontSize: 10, bgcolor: 'divider', color: 'text.secondary' }} />
            {game.eco && <Chip label={game.eco} size="small" sx={{ height: 18, fontSize: 10, bgcolor: 'primary.dark', color: 'primary.contrastText' }} />}
            {game.date && <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: 10 }}>{game.date}</Typography>}
            {game.event && <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: 10, ml: 0.5 }}>· {game.event}</Typography>}
          </Box>
        )}
      </Box>

      {/* Move list — tree mode (editable) or flat mode */}
      {/* Tree mode: the notation scrolls itself and keeps its action bar pinned below. */}
      <Box sx={useTreeMode
        ? { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }
        : { flex: 1, overflow: 'auto', p: 1, maxHeight: { xs: 150, lg: 'none' } }}
      >
        {useTreeMode && MoveNotation ? (
          <MoveNotation
            tree={editTree}
            selectedNodeId={editSelectedNodeId || null}
            onNodeSelect={onEditNodeSelect}
            loading={false}
            contextMenuActions={editContextMenuActions}
            voiceNotes={voiceNotes}
            showComments
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

      {isEditable && saveStatus !== 'idle' && (
        <Box
          role="status"
          sx={{ display: 'flex', alignItems: 'center', gap: 0.75, px: 1.5, py: 0.5, borderBottom: 1, borderColor: 'divider' }}
        >
          {saveStatus === 'saving' && (
            <>
              <CircularProgress size={10} />
              <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 11 }}>
                {t('myGames.autoSave.saving')}
              </Typography>
            </>
          )}
          {saveStatus === 'saved' && (
            <Typography variant="caption" sx={{ color: 'success.main', fontSize: 11 }}>
              {t('myGames.autoSave.saved')} ✓
            </Typography>
          )}
          {saveStatus === 'error' && (
            <>
              <Typography variant="caption" sx={{ color: 'error.main', fontSize: 11 }}>
                {t('myGames.autoSave.saveFailed')} ·
              </Typography>
              <Button
                size="small"
                onClick={onRetrySave}
                sx={{ textTransform: 'none', fontSize: 11, minWidth: 0, p: 0, lineHeight: 1.5 }}
              >
                {t('myGames.autoSave.retry')}
              </Button>
            </>
          )}
        </Box>
      )}

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
            {t('myGames.autoSave.saveNow')}
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

      {/* Delete confirmation dialog */}
      <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)}>
        <DialogTitle>Delete Game</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to delete this game? This action cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleDeleteConfirm} color="error" variant="contained">Delete</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
