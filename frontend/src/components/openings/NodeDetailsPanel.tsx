'use client';

import React, { useState, useEffect } from 'react';
import {
  Box, Typography, TextField, IconButton, Button, Chip, Divider,
  LinearProgress, Dialog, DialogTitle, DialogContent, DialogActions, Tooltip, List, ListItem, ListItemText,
} from '@mui/material';
import {
  Star, StarBorder, Delete, Edit, Search, ContentCopy,
  CheckCircle, Schedule, Close,
} from '@mui/icons-material';
import type { OpeningNode, GameLink } from '@/hooks/useOpeningRepertoire';

interface NodeDetailsPanelProps {
  node: OpeningNode | null;
  onUpdateNotes: (nodeId: string, notes: string) => Promise<void>;
  onToggleCritical: (nodeId: string, isCritical: boolean) => Promise<void>;
  onDeleteNode: (nodeId: string) => Promise<void>;
  onSearchGames: (fen: string) => void;
  gameLinks: GameLink[];
  gameLinksLoading: boolean;
}

export default function NodeDetailsPanel({
  node, onUpdateNotes, onToggleCritical, onDeleteNode,
  onSearchGames, gameLinks, gameLinksLoading,
}: NodeDetailsPanelProps) {
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
        <Typography variant="body2">Select a move to view details.</Typography>
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

  let moveDisplay = '(starting position)';
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
        <Tooltip title="Copy FEN">
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
            Notes
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
              placeholder="Add notes about this position..."
              sx={{
                '& .MuiInputBase-root': { color: '#e0e0e0', bgcolor: '#2a2a2a', fontSize: 13 },
                '& .MuiOutlinedInput-notchedOutline': { borderColor: '#444' },
              }}
            />
            <Box sx={{ display: 'flex', gap: 1, mt: 0.5 }}>
              <Button size="small" variant="contained" onClick={handleSaveNotes} sx={{ fontSize: 11 }}>Save</Button>
              <Button size="small" onClick={() => setEditingNotes(false)} sx={{ color: '#aaa', fontSize: 11 }}>Cancel</Button>
            </Box>
          </Box>
        ) : (
          <Typography variant="body2" sx={{ color: node.notes ? '#ccc' : '#666', fontSize: 13, fontStyle: node.notes ? 'normal' : 'italic' }}>
            {node.notes || 'No notes'}
          </Typography>
        )}
      </Box>

      {/* Training stats (non-root only) */}
      {!isRoot && (
        <>
          <Divider sx={{ borderColor: '#333' }} />
          <Box>
            <Typography variant="caption" sx={{ color: '#aaa', fontWeight: 600, textTransform: 'uppercase', fontSize: 11, mb: 0.5, display: 'block' }}>
              Training
            </Typography>

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              {isMastered && <Chip icon={<CheckCircle />} label="Mastered" size="small" sx={{ bgcolor: '#1b5e20', color: '#fff' }} />}
              {needsReview && !isMastered && <Chip icon={<Schedule />} label="Due for Review" size="small" sx={{ bgcolor: '#e65100', color: '#fff' }} />}
              {isUntrained && <Chip label="Untrained" size="small" sx={{ bgcolor: '#333', color: '#888' }} />}
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
            {node.is_critical ? 'Critical ★' : 'Mark Critical'}
          </Button>
        )}

        <Button
          size="small"
          startIcon={<Search />}
          onClick={() => onSearchGames(node.fen)}
          sx={{ color: '#aaa', fontSize: 11, textTransform: 'none' }}
        >
          Search Games
        </Button>

        {!isRoot && (
          <Button
            size="small"
            startIcon={<Delete />}
            onClick={() => setDeleteOpen(true)}
            sx={{ color: '#f44336', fontSize: 11, textTransform: 'none' }}
          >
            Delete
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
                    primary={`${g.white_player || '?'} vs ${g.black_player || '?'}`}
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
        <DialogTitle>Delete Move?</DialogTitle>
        <DialogContent>
          <Typography>Delete <strong>{moveDisplay}</strong> and all child moves? This cannot be undone.</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteOpen(false)} sx={{ color: '#aaa' }}>Cancel</Button>
          <Button onClick={() => { onDeleteNode(node.id); setDeleteOpen(false); }} color="error" variant="contained">Delete</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
