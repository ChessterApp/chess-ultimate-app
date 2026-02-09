'use client';

import React, { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import {
  Box, Typography, TextField, IconButton, Button, Chip, Divider,
  LinearProgress, Dialog, DialogTitle, DialogContent, DialogActions, Tooltip, List, ListItem, ListItemText,
  CircularProgress,
} from '@mui/material';
import {
  Star, StarBorder, Delete, Edit, Search, ContentCopy,
  CheckCircle, Schedule, Close, Storage,
} from '@mui/icons-material';
import type { OpeningNode, GameLink, GameSearchResult } from '@/hooks/useOpeningRepertoire';

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
}

export default function NodeDetailsPanel({
  node, onUpdateNotes, onToggleCritical, onDeleteNode,
  onSearchGames, gameLinks, gameLinksLoading,
  masterGames = [], masterGamesTotal = 0, masterGamesLoading = false,
  onOpenGame,
}: NodeDetailsPanelProps) {
  const t = useTranslations('debut');
  const [editingNotes, setEditingNotes] = useState(false);
  const [notesText, setNotesText] = useState('');
  const [deleteOpen, setDeleteOpen] = useState(false);

  useEffect(() => {
    setEditingNotes(false);
    setNotesText(node?.notes || '');
  }, [node?.id]);

  if (!node) {
    return (
      <Box sx={{ p: 2, color: '#888' }}>
        <Typography variant="body2">{t('selectMoveDetails')}</Typography>
      </Box>
    );
  }

  const isRoot = node.move_san === null;
  const accuracy = node.times_trained > 0 ? (node.times_correct / node.times_trained * 100) : 0;
  const accuracyColor = accuracy >= 80 ? '#4caf50' : accuracy >= 60 ? '#ff9800' : '#f44336';

  const isMastered = node.times_trained >= 5 && accuracy >= 80;
  const needsReview = node.next_review_at ? new Date(node.next_review_at) <= new Date() : false;
  const isUntrained = node.times_trained === 0;

  const handleSaveNotes = async () => {
    await onUpdateNotes(node.id, notesText);
    setEditingNotes(false);
  };

  const handleCopyFen = () => {
    navigator.clipboard.writeText(node.fen);
  };

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
            <Chip label={node.eco_code} size="small" sx={{ bgcolor: '#5c6bc0', color: '#fff', fontWeight: 600, fontSize: 12 }} />
          )}
          {node.opening_name && (
            <Typography variant="body2" sx={{ color: '#b0bec5', fontWeight: 500 }}>
              {node.opening_name}
            </Typography>
          )}
        </Box>
      )}

      {/* Move display */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Typography variant="h6" sx={{ color: '#e0e0e0', fontFamily: 'monospace', fontSize: 18 }}>
          {moveDisplay}
        </Typography>
      </Box>

      {/* FEN */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <Typography
          variant="caption"
          sx={{ fontFamily: 'monospace', color: '#777', fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}
        >
          {node.fen}
        </Typography>
        <Tooltip title={t('copyFen')}>
          <IconButton size="small" onClick={handleCopyFen} sx={{ color: '#777', p: 0.3 }}>
            <ContentCopy sx={{ fontSize: 14 }} />
          </IconButton>
        </Tooltip>
      </Box>

      <Divider sx={{ borderColor: '#333' }} />

      {/* Notes */}
      <Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
          <Typography variant="caption" sx={{ color: '#aaa', fontWeight: 600, textTransform: 'uppercase', fontSize: 11 }}>
            {t('notes')}
          </Typography>
          {!editingNotes && (
            <IconButton size="small" onClick={() => { setNotesText(node.notes || ''); setEditingNotes(true); }} sx={{ color: '#777', p: 0.3 }}>
              <Edit sx={{ fontSize: 14 }} />
            </IconButton>
          )}
        </Box>

        {editingNotes ? (
          <Box>
            <TextField
              multiline
              rows={3}
              value={notesText}
              onChange={e => setNotesText(e.target.value)}
              fullWidth
              size="small"
              placeholder={t('addNotesPlaceholder')}
              sx={{
                '& .MuiInputBase-root': { color: '#e0e0e0', bgcolor: '#2a2a2a', fontSize: 13 },
                '& .MuiOutlinedInput-notchedOutline': { borderColor: '#444' },
              }}
            />
            <Box sx={{ display: 'flex', gap: 1, mt: 0.5 }}>
              <Button size="small" variant="contained" onClick={handleSaveNotes} sx={{ fontSize: 11 }}>{t('save')}</Button>
              <Button size="small" onClick={() => setEditingNotes(false)} sx={{ color: '#aaa', fontSize: 11 }}>{t('cancel')}</Button>
            </Box>
          </Box>
        ) : (
          <Typography variant="body2" sx={{ color: node.notes ? '#ccc' : '#666', fontSize: 13, fontStyle: node.notes ? 'normal' : 'italic' }}>
            {node.notes || t('noNotes')}
          </Typography>
        )}
      </Box>

      {/* Master Games (auto-fetched from TWIC) */}
      <Divider sx={{ borderColor: '#333' }} />
      <Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
          <Storage sx={{ fontSize: 14, color: '#7986cb' }} />
          <Typography variant="caption" sx={{ color: '#aaa', fontWeight: 600, textTransform: 'uppercase', fontSize: 11 }}>
            {t('masterGames')}
          </Typography>
          {masterGamesTotal > 0 && (
            <Chip
              label={masterGamesTotal.toLocaleString()}
              size="small"
              sx={{ height: 16, fontSize: 10, bgcolor: '#3949ab', color: '#fff', ml: 'auto' }}
            />
          )}
        </Box>

        {masterGamesLoading ? (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 1 }}>
            <CircularProgress size={14} sx={{ color: '#7986cb' }} />
            <Typography variant="caption" sx={{ color: '#777' }}>{t('searchingPosition')}</Typography>
          </Box>
        ) : masterGames.length > 0 ? (
          <Box>
            <List dense sx={{ p: 0 }}>
              {masterGames.map((g, idx) => (
                <ListItem
                  key={`master-${g.id || idx}`}
                  sx={{ px: 0, py: 0.3, cursor: onOpenGame ? 'pointer' : 'default', '&:hover': onOpenGame ? { bgcolor: 'rgba(255,255,255,0.04)' } : {} }}
                  onClick={() => onOpenGame?.(g)}
                >
                  <ListItemText
                    primary={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <Typography component="span" sx={{ color: '#e0e0e0', fontSize: 12 }}>
                          {g.white_name || g.white || '?'}
                        </Typography>
                        <Typography component="span" sx={{ color: '#777', fontSize: 10 }}>
                          ({g.white_elo || '?'})
                        </Typography>
                        <Typography component="span" sx={{ color: '#888', fontSize: 11 }}>{t('vs')}</Typography>
                        <Typography component="span" sx={{ color: '#e0e0e0', fontSize: 12 }}>
                          {g.black_name || g.black || '?'}
                        </Typography>
                        <Typography component="span" sx={{ color: '#777', fontSize: 10 }}>
                          ({g.black_elo || '?'})
                        </Typography>
                      </Box>
                    }
                    secondary={
                      <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', mt: 0.2 }}>
                        <Chip label={g.result || '?'} size="small" sx={{ height: 14, fontSize: 9, bgcolor: '#444', color: '#ccc' }} />
                        {g.eco && <Chip label={g.eco} size="small" sx={{ height: 14, fontSize: 9, bgcolor: '#3949ab', color: '#fff' }} />}
                        {(g.date || g.year) && (
                          <Typography component="span" sx={{ color: '#666', fontSize: 10 }}>
                            {g.date || g.year}
                          </Typography>
                        )}
                      </Box>
                    }
                  />
                </ListItem>
              ))}
            </List>
            {masterGamesTotal > 5 && (
              <Button
                size="small"
                onClick={() => onSearchGames(node!.fen)}
                sx={{ color: '#7986cb', fontSize: 11, textTransform: 'none', mt: 0.5 }}
              >
                {t('viewAllGames', { count: masterGamesTotal.toLocaleString() })}
              </Button>
            )}
          </Box>
        ) : (
          <Typography variant="body2" sx={{ color: '#555', fontSize: 12, fontStyle: 'italic' }}>
            {t('noMasterGames')}
          </Typography>
        )}
      </Box>

      {/* Training stats (non-root only) */}
      {!isRoot && (
        <>
          <Divider sx={{ borderColor: '#333' }} />
          <Box>
            <Typography variant="caption" sx={{ color: '#aaa', fontWeight: 600, textTransform: 'uppercase', fontSize: 11, mb: 0.5, display: 'block' }}>
              {t('training')}
            </Typography>

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              {isMastered && <Chip icon={<CheckCircle />} label="Mastered" size="small" sx={{ bgcolor: '#1b5e20', color: '#fff' }} />}
              {needsReview && !isMastered && <Chip icon={<Schedule />} label="Due for Review" size="small" sx={{ bgcolor: '#e65100', color: '#fff' }} />}
              {isUntrained && <Chip label={t('untrained')} size="small" sx={{ bgcolor: '#333', color: '#888' }} />}
            </Box>

            {node.times_trained > 0 && (
              <Box sx={{ mb: 0.5 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.3 }}>
                  <Typography variant="caption" sx={{ color: '#aaa', fontSize: 11 }}>
                    Accuracy: {accuracy.toFixed(0)}%
                  </Typography>
                  <Typography variant="caption" sx={{ color: '#aaa', fontSize: 11 }}>
                    {node.times_correct}/{node.times_trained}
                  </Typography>
                </Box>
                <LinearProgress
                  variant="determinate"
                  value={accuracy}
                  sx={{ height: 4, borderRadius: 2, bgcolor: '#333', '& .MuiLinearProgress-bar': { bgcolor: accuracyColor } }}
                />
              </Box>
            )}

            {node.next_review_at && (
              <Typography variant="caption" sx={{ color: '#777', fontSize: 10 }}>
                Next review: {new Date(node.next_review_at).toLocaleDateString()}
              </Typography>
            )}
          </Box>
        </>
      )}

      <Divider sx={{ borderColor: '#333' }} />

      {/* Actions */}
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
        {!isRoot && (
          <Button
            size="small"
            startIcon={node.is_critical ? <Star /> : <StarBorder />}
            onClick={() => onToggleCritical(node.id, !node.is_critical)}
            sx={{
              color: node.is_critical ? '#ffd700' : '#aaa', fontSize: 11, textTransform: 'none',
            }}
          >
            {node.is_critical ? t('critical') : t('markCritical')}
          </Button>
        )}

        <Button
          size="small"
          startIcon={<Search />}
          onClick={() => onSearchGames(node.fen)}
          sx={{ color: '#aaa', fontSize: 11, textTransform: 'none' }}
        >
          {t('searchGames')}
        </Button>

        {!isRoot && (
          <Button
            size="small"
            startIcon={<Delete />}
            onClick={() => setDeleteOpen(true)}
            sx={{ color: '#f44336', fontSize: 11, textTransform: 'none' }}
          >
            {t('delete')}
          </Button>
        )}
      </Box>

      {/* Linked games */}
      {gameLinks.length > 0 && (
        <>
          <Divider sx={{ borderColor: '#333' }} />
          <Box>
            <Typography variant="caption" sx={{ color: '#aaa', fontWeight: 600, textTransform: 'uppercase', fontSize: 11, mb: 0.5, display: 'block' }}>
              Linked Games ({gameLinks.length})
            </Typography>
            <List dense sx={{ p: 0 }}>
              {gameLinks.map(g => (
                <ListItem key={g.id} sx={{ px: 0, py: 0.3 }}>
                  <ListItemText
                    primary={`${g.white_player || '?'} ${t('vs')} ${g.black_player || '?'}`}
                    secondary={`${g.result || ''} · ${g.date_played || ''}`}
                    primaryTypographyProps={{ sx: { color: '#ccc', fontSize: 12 } }}
                    secondaryTypographyProps={{ sx: { color: '#777', fontSize: 10 } }}
                  />
                  <Chip label={g.game_source} size="small" sx={{ height: 16, fontSize: 9, bgcolor: '#333', color: '#aaa' }} />
                </ListItem>
              ))}
            </List>
          </Box>
        </>
      )}

      {/* Delete confirmation */}
      <Dialog open={deleteOpen} onClose={() => setDeleteOpen(false)} PaperProps={{ sx: { bgcolor: '#2a2a2a', color: '#e0e0e0' } }}>
        <DialogTitle>{t('deleteMoveTitle')}</DialogTitle>
        <DialogContent>
          <Typography>{t('deleteMoveConfirm', { move: moveDisplay })}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteOpen(false)} sx={{ color: '#aaa' }}>{t('cancel')}</Button>
          <Button onClick={() => { onDeleteNode(node.id); setDeleteOpen(false); }} color="error" variant="contained">{t('delete')}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
