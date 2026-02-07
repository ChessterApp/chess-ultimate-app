'use client';

/**
 * RepertoireItem Component
 * Individual opening card with edit and delete functionality
 */

import React, { useState } from 'react';
import {
  Card,
  CardContent,
  CardActions,
  Box,
  Typography,
  IconButton,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  Tooltip,
  CircularProgress,
} from '@mui/material';
import {
  Edit as EditIcon,
  Delete as DeleteIcon,
  Favorite as FavoriteIcon,
  FavoriteBorder as FavoriteBorderIcon,
  School as StudyIcon,
} from '@mui/icons-material';
import { useTranslations } from 'next-intl';

import { RepertoireOpening, UpdateOpeningRequest } from '@/types/repertoire';

interface RepertoireItemProps {
  opening: RepertoireOpening;
  onUpdate: (openingId: string, updates: UpdateOpeningRequest) => Promise<void>;
  onRemove: (openingId: string) => Promise<void>;
}

export default function RepertoireItem({
  opening,
  onUpdate,
  onRemove,
}: RepertoireItemProps) {
  const t = useTranslations();
  const [editingNotes, setEditingNotes] = useState(false);
  const [notes, setNotes] = useState(opening.notes || '');
  const [updating, setUpdating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const handleSaveNotes = async () => {
    if (notes === opening.notes) {
      setEditingNotes(false);
      return;
    }

    setUpdating(true);
    try {
      await onUpdate(opening.opening_id, { notes });
      setEditingNotes(false);
    } finally {
      setUpdating(false);
    }
  };

  const handleToggleFavorite = async () => {
    setUpdating(true);
    try {
      await onUpdate(opening.opening_id, { favorite: !opening.favorite });
    } finally {
      setUpdating(false);
    }
  };

  const handleConfirmDelete = async () => {
    setDeleting(true);
    try {
      await onRemove(opening.opening_id);
    } finally {
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  const getColorBadge = () => {
    switch (opening.color) {
      case 'white':
        return '#FFFFFF';
      case 'black':
        return '#000000';
      default:
        return '#999999';
    }
  };

  return (
    <>
      <Card
        variant="outlined"
        sx={{
          '&:hover': {
            boxShadow: 2,
          },
          transition: 'all 0.2s ease',
        }}
      >
        <CardContent sx={{ pb: 1 }}>
          {/* Header: Name and Color Badge */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
            {/* Color indicator */}
            <Box
              sx={{
                width: 16,
                height: 16,
                borderRadius: '50%',
                backgroundColor: getColorBadge(),
                border: '1px solid #ccc',
                flexShrink: 0,
              }}
            />

            <Typography variant="subtitle1" sx={{ fontWeight: 600, flex: 1 }}>
              {opening.opening_name}
            </Typography>

            {opening.eco_code && (
              <Chip
                label={opening.eco_code}
                size="small"
                variant="outlined"
                sx={{ ml: 1 }}
              />
            )}
          </Box>

          {/* Moves */}
          {opening.first_moves && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
              {opening.first_moves}
            </Typography>
          )}

          {/* Notes Section */}
          {editingNotes ? (
            <TextField
              fullWidth
              multiline
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={t('repertoire.addNotes')}
              size="small"
              sx={{ mb: 1 }}
              disabled={updating}
            />
          ) : (
            opening.notes && (
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1, fontStyle: 'italic' }}>
                {opening.notes}
              </Typography>
            )
          )}

          {/* Tags */}
          {opening.tags && opening.tags.length > 0 && (
            <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mb: 1 }}>
              {opening.tags.map((tag) => (
                <Chip
                  key={tag}
                  label={tag}
                  size="small"
                  variant="filled"
                  sx={{
                    height: 24,
                    fontSize: '0.75rem',
                  }}
                />
              ))}
            </Box>
          )}

          {/* Metadata */}
          <Typography variant="caption" color="text.secondary">
            {t('repertoire.added')} {new Date(opening.created_at).toLocaleDateString()}
          </Typography>
        </CardContent>

        {/* Actions */}
        <CardActions sx={{ pt: 0, pb: 1, display: 'flex', justifyContent: 'flex-end', gap: 0.5 }}>
          {/* Study Mode Button */}
          <Tooltip title={t('repertoire.studyMode')}>
            <IconButton size="small" disabled={updating || deleting}>
              <StudyIcon fontSize="small" />
            </IconButton>
          </Tooltip>

          {/* Toggle Favorite */}
          <Tooltip title={opening.favorite ? 'Remove favorite' : 'Add to favorites'}>
            <IconButton
              size="small"
              onClick={handleToggleFavorite}
              disabled={updating || deleting}
            >
              {opening.favorite ? (
                <FavoriteIcon fontSize="small" sx={{ color: 'error.main' }} />
              ) : (
                <FavoriteBorderIcon fontSize="small" />
              )}
            </IconButton>
          </Tooltip>

          {/* Edit Notes */}
          <Tooltip title="Edit notes">
            <IconButton
              size="small"
              onClick={() => {
                if (editingNotes) {
                  handleSaveNotes();
                } else {
                  setEditingNotes(true);
                }
              }}
              disabled={updating || deleting}
            >
              {updating ? (
                <CircularProgress size={20} />
              ) : (
                <EditIcon fontSize="small" />
              )}
            </IconButton>
          </Tooltip>

          {/* Delete */}
          <Tooltip title={t('repertoire.remove')}>
            <IconButton
              size="small"
              onClick={() => setConfirmDelete(true)}
              disabled={updating || deleting}
              sx={{ color: 'error.main' }}
            >
              {deleting ? <CircularProgress size={20} /> : <DeleteIcon fontSize="small" />}
            </IconButton>
          </Tooltip>
        </CardActions>
      </Card>

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>{t('repertoire.removeConfirmTitle')}</DialogTitle>
        <DialogContent>
          <Typography>{t('repertoire.removeConfirm', { name: opening.opening_name })}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDelete(false)}>{t('common.cancel')}</Button>
          <Button
            onClick={handleConfirmDelete}
            color="error"
            variant="contained"
            disabled={deleting}
          >
            {deleting ? <CircularProgress size={20} /> : t('common.delete')}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
