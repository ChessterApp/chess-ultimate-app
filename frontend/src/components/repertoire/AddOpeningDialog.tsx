'use client';

/**
 * AddOpeningDialog Component
 * Dialog for adding a new opening to repertoire with metadata
 */

import React, { useState } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Box,
  Typography,
  Button,
  CircularProgress,
  Chip,
  Stack,
} from '@mui/material';
import { useTranslations } from 'next-intl';

import { AddOpeningRequest } from '@/types/repertoire';

interface OpeningSearchResult {
  id: string;
  name: string;
  eco_code: string;
  moves: string;
  description?: string;
}

interface AddOpeningDialogProps {
  opening: OpeningSearchResult;
  onAdd: (request: AddOpeningRequest) => Promise<void>;
  onClose: () => void;
  loading?: boolean;
}

export default function AddOpeningDialog({
  opening,
  onAdd,
  onClose,
  loading = false,
}: AddOpeningDialogProps) {
  const t = useTranslations();
  const [color, setColor] = useState<'white' | 'black' | 'both'>('white');
  const [notes, setNotes] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState('');

  const handleAddTag = () => {
    if (tagInput.trim() && !tags.includes(tagInput.trim())) {
      setTags([...tags, tagInput.trim()]);
      setTagInput('');
    }
  };

  const handleRemoveTag = (tagToRemove: string) => {
    setTags(tags.filter((t) => t !== tagToRemove));
  };

  const handleAdd = async () => {
    const request: AddOpeningRequest = {
      opening_id: opening.id,
      opening_name: opening.name,
      color,
      eco_code: opening.eco_code,
      first_moves: opening.moves,
      notes,
      tags: tags.length > 0 ? tags : undefined,
    };

    await onAdd(request);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleAddTag();
    }
  };

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('repertoire.addOpeningTitle')}</DialogTitle>

      <DialogContent sx={{ pt: 2 }}>
        {/* Opening Details */}
        <Box sx={{ mb: 3, p: 2, backgroundColor: 'action.hover', borderRadius: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
            {opening.name}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
            {t('repertoire.eco')}: {opening.eco_code}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
            {opening.moves}
          </Typography>
        </Box>

        {/* Color Selection */}
        <FormControl fullWidth sx={{ mb: 2 }}>
          <InputLabel>{t('repertoire.colorLabel')}</InputLabel>
          <Select value={color} label={t('repertoire.colorLabel')} onChange={(e) => setColor(e.target.value as any)}>
            <MenuItem value="white">{t('repertoire.colorFilter.white')}</MenuItem>
            <MenuItem value="black">{t('repertoire.colorFilter.black')}</MenuItem>
            <MenuItem value="both">{t('repertoire.colorBoth')}</MenuItem>
          </Select>
        </FormControl>

        {/* Notes Field */}
        <TextField
          fullWidth
          multiline
          rows={3}
          label={t('repertoire.notesLabel')}
          placeholder={t('repertoire.addNotes')}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          sx={{ mb: 2 }}
          disabled={loading}
        />

        {/* Tags Section */}
        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 500, mb: 1 }}>
            {t('repertoire.tags')}
          </Typography>

          {/* Tag Input */}
          <Box sx={{ display: 'flex', gap: 1, mb: 1 }}>
            <TextField
              size="small"
              placeholder={t('repertoire.addTagPlaceholder')}
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyPress={handleKeyPress}
              disabled={loading}
              sx={{ flex: 1 }}
            />
            <Button
              variant="outlined"
              size="small"
              onClick={handleAddTag}
              disabled={loading || !tagInput.trim()}
            >
              {t('common.add')}
            </Button>
          </Box>

          {/* Tag Display */}
          {tags.length > 0 && (
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
              {tags.map((tag) => (
                <Chip
                  key={tag}
                  label={tag}
                  onDelete={() => handleRemoveTag(tag)}
                  disabled={loading}
                  size="small"
                />
              ))}
            </Stack>
          )}
        </Box>
      </DialogContent>

      <DialogActions sx={{ p: 2 }}>
        <Button onClick={onClose} disabled={loading}>
          {t('common.cancel')}
        </Button>
        <Button
          onClick={handleAdd}
          variant="contained"
          disabled={loading}
          startIcon={loading && <CircularProgress size={20} />}
        >
          {t('repertoire.addToRepertoire')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
