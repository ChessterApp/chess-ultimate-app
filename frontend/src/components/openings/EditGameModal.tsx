/**
 * EditGameModal — Modal for editing game metadata (title, players, result, etc.)
 */

'use client';

import React, { useState, useCallback, useEffect, useRef } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  Box,
  Typography,
  TextField,
  Button,
  IconButton,
  Alert,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  CircularProgress,
} from '@mui/material';
import { Close } from '@mui/icons-material';
import { useTranslations } from 'next-intl';
import type { UserGame } from '@/hooks/useUserGames';

interface GameFormData {
  title: string;
  white: string;
  black: string;
  whiteElo: string;
  blackElo: string;
  result: string;
  date: string;
  event: string;
  openingName: string;
  notes: string;
}

interface EditGameModalProps {
  open: boolean;
  onClose: () => void;
  game: UserGame | null;
  onSave: (id: string, updates: Partial<Omit<UserGame, 'id' | 'user_id' | 'created_at'>>) => Promise<UserGame | null>;
}

const fieldSx = {
  '& .MuiOutlinedInput-root': {
    fontSize: 12,
    bgcolor: 'action.hover',
  },
  '& .MuiInputLabel-root': {
    fontSize: 12,
  },
};

function gameToForm(game: UserGame): GameFormData {
  return {
    title: game.title || '',
    white: game.white || '',
    black: game.black || '',
    whiteElo: game.white_elo != null ? String(game.white_elo) : '',
    blackElo: game.black_elo != null ? String(game.black_elo) : '',
    result: game.result || '*',
    date: game.date || '',
    event: game.event || '',
    openingName: game.opening_name || '',
    notes: game.notes || '',
  };
}

export default function EditGameModal({ open, onClose, game, onSave }: EditGameModalProps) {
  const t = useTranslations('debut');
  const [form, setForm] = useState<GameFormData>({
    title: '', white: '', black: '', whiteElo: '', blackElo: '',
    result: '*', date: '', event: '', openingName: '', notes: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const initialFormRef = useRef<GameFormData | null>(null);

  // Populate form when game changes
  useEffect(() => {
    if (game && open) {
      const formData = gameToForm(game);
      setForm(formData);
      initialFormRef.current = formData;
      setError('');
      setSaving(false);
    }
  }, [game, open]);

  const handleClose = useCallback(() => {
    setError('');
    setSaving(false);
    onClose();
  }, [onClose]);

  const updateField = (field: keyof GameFormData, value: string) => {
    setForm(prev => ({ ...prev, [field]: value }));
  };

  const handleSave = useCallback(async () => {
    if (!game || !initialFormRef.current) return;

    const initial = initialFormRef.current;
    const updates: Record<string, unknown> = {};

    if (form.title !== initial.title) updates.title = form.title || null;
    if (form.white !== initial.white) updates.white = form.white;
    if (form.black !== initial.black) updates.black = form.black;
    if (form.whiteElo !== initial.whiteElo) updates.white_elo = form.whiteElo ? parseInt(form.whiteElo, 10) : null;
    if (form.blackElo !== initial.blackElo) updates.black_elo = form.blackElo ? parseInt(form.blackElo, 10) : null;
    if (form.result !== initial.result) updates.result = form.result;
    if (form.date !== initial.date) updates.date = form.date || null;
    if (form.event !== initial.event) updates.event = form.event || null;
    if (form.openingName !== initial.openingName) updates.opening_name = form.openingName || null;
    if (form.notes !== initial.notes) updates.notes = form.notes || null;

    if (Object.keys(updates).length === 0) {
      setError(t('myGames.editModal.noChanges'));
      return;
    }

    setError('');
    setSaving(true);
    try {
      const result = await onSave(game.id, updates as Parameters<typeof onSave>[1]);
      if (result) {
        handleClose();
      } else {
        setError(t('myGames.editModal.updateFailed'));
      }
    } catch {
      setError(t('myGames.editModal.updateFailed'));
    } finally {
      setSaving(false);
    }
  }, [game, form, onSave, handleClose, t]);

  if (!game) return null;

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="sm"
      fullWidth
      PaperProps={{
        sx: {
          bgcolor: 'background.paper',
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 2,
          maxHeight: '90vh',
        },
      }}
      slotProps={{
        backdrop: {
          sx: {
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            backdropFilter: 'blur(4px)',
          },
        },
      }}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', pb: 1 }}>
        <Typography sx={{ fontSize: 16, fontWeight: 600, color: 'text.primary' }}>
          {t('myGames.editModal.title')}
        </Typography>
        <IconButton onClick={handleClose} size="small" sx={{ color: 'text.secondary' }}>
          <Close fontSize="small" />
        </IconButton>
      </DialogTitle>

      <DialogContent sx={{ px: 3, pb: 3 }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          <Typography sx={{ fontSize: 12, fontWeight: 600, color: 'text.secondary', textTransform: 'uppercase', letterSpacing: 0.5 }}>
            {t('myGames.addModal.gameDetails')}
          </Typography>

          <TextField
            size="small"
            label={t('myGames.addModal.titleLabel')}
            value={form.title}
            onChange={(e) => updateField('title', e.target.value)}
            sx={fieldSx}
          />

          <Box sx={{ display: 'flex', gap: 1 }}>
            <TextField
              size="small"
              label={t('myGames.addModal.whiteName')}
              value={form.white}
              onChange={(e) => updateField('white', e.target.value)}
              sx={{ ...fieldSx, flex: 1 }}
            />
            <TextField
              size="small"
              label={t('myGames.addModal.whiteElo')}
              value={form.whiteElo}
              onChange={(e) => updateField('whiteElo', e.target.value.replace(/\D/g, ''))}
              sx={{ ...fieldSx, width: 80 }}
            />
          </Box>

          <Box sx={{ display: 'flex', gap: 1 }}>
            <TextField
              size="small"
              label={t('myGames.addModal.blackName')}
              value={form.black}
              onChange={(e) => updateField('black', e.target.value)}
              sx={{ ...fieldSx, flex: 1 }}
            />
            <TextField
              size="small"
              label={t('myGames.addModal.blackElo')}
              value={form.blackElo}
              onChange={(e) => updateField('blackElo', e.target.value.replace(/\D/g, ''))}
              sx={{ ...fieldSx, width: 80 }}
            />
          </Box>

          <Box sx={{ display: 'flex', gap: 1 }}>
            <FormControl size="small" sx={{ flex: 1 }}>
              <InputLabel sx={{ fontSize: 12 }}>{t('myGames.addModal.resultLabel')}</InputLabel>
              <Select
                value={form.result}
                onChange={(e) => updateField('result', e.target.value)}
                label={t('myGames.addModal.resultLabel')}
                sx={{ fontSize: 12, bgcolor: 'action.hover' }}
              >
                <MenuItem value="*">*</MenuItem>
                <MenuItem value="1-0">1-0</MenuItem>
                <MenuItem value="0-1">0-1</MenuItem>
                <MenuItem value="1/2-1/2">1/2-1/2</MenuItem>
              </Select>
            </FormControl>
            <TextField
              size="small"
              label={t('myGames.addModal.dateLabel')}
              placeholder="YYYY.MM.DD"
              value={form.date}
              onChange={(e) => updateField('date', e.target.value)}
              sx={{ ...fieldSx, flex: 1 }}
            />
          </Box>

          <TextField
            size="small"
            label={t('myGames.addModal.eventLabel')}
            value={form.event}
            onChange={(e) => updateField('event', e.target.value)}
            sx={fieldSx}
          />

          <TextField
            size="small"
            label={t('myGames.addModal.notesLabel')}
            value={form.notes}
            onChange={(e) => updateField('notes', e.target.value)}
            multiline
            rows={2}
            sx={fieldSx}
          />
        </Box>

        {/* Error */}
        {error && (
          <Alert severity="error" sx={{ mt: 2, fontSize: 12 }} onClose={() => setError('')}>
            {error}
          </Alert>
        )}

        {/* Actions */}
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 1.5, mt: 2.5 }}>
          <Button
            onClick={handleClose}
            size="small"
            sx={{
              color: 'text.secondary',
              fontSize: 12,
              textTransform: 'none',
              '&:hover': { bgcolor: 'action.hover' },
            }}
          >
            {t('myGames.cancel')}
          </Button>
          <Button
            variant="contained"
            size="small"
            onClick={handleSave}
            disabled={saving}
            sx={{
              fontSize: 12,
              textTransform: 'none',
              px: 3,
              background: 'linear-gradient(135deg, #7c3aed, #6366f1)',
              '&:hover': { background: 'linear-gradient(135deg, #6d28d9, #4f46e5)' },
            }}
          >
            {saving ? <CircularProgress size={16} sx={{ color: '#fff' }} /> : t('myGames.editModal.saveChanges')}
          </Button>
        </Box>
      </DialogContent>
    </Dialog>
  );
}
