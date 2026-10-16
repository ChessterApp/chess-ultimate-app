'use client';

/**
 * MoveActionSheet — bottom sheet with the move actions on touch / narrow
 * screens, where the notation's right-click menu is unreachable. Renders the
 * same action list as the desktop menu, plus full-size symbol and comment
 * editors.
 */
import React, { useState } from 'react';
import { Box, Button, ButtonBase, Drawer, TextField, Typography } from '@mui/material';
import NagPalette, { type NagPaletteLabels } from './NagPalette';

export type MoveSheetView = 'actions' | 'nags' | 'comment';

export interface MoveAction {
  key: string;
  label: string;
  icon: React.ReactNode;
  color?: string;
}

interface MoveActionSheetProps {
  open: boolean;
  view: MoveSheetView;
  title: string;
  actions: MoveAction[];
  onAction: (key: string) => void;
  onClose: () => void;
  nags?: number[];
  onNagToggle?: (code: number) => void;
  nagLabels?: NagPaletteLabels;
  comment: string;
  onCommentSave: (text: string) => void;
  labels: { commentPlaceholder?: string; save: string; cancel: string };
}

function CommentForm({ initial, placeholder, save, cancel, onSave, onCancel }: {
  initial: string;
  placeholder?: string;
  save: string;
  cancel: string;
  onSave: (text: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initial);
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, px: 1 }}>
      <TextField
        autoFocus
        multiline
        minRows={3}
        maxRows={8}
        fullWidth
        value={value}
        placeholder={placeholder}
        onChange={(e) => setValue(e.target.value)}
        slotProps={{ htmlInput: { 'aria-label': placeholder, 'data-testid': 'move-comment-sheet-input' } }}
        sx={{ '& .MuiOutlinedInput-root': { fontSize: 16 } }}
      />
      <Box sx={{ display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
        <Button onClick={onCancel} sx={{ minHeight: 44, textTransform: 'none', color: 'text.secondary' }}>
          {cancel}
        </Button>
        <Button variant="contained" onClick={() => onSave(value)} sx={{ minHeight: 44, px: 3, textTransform: 'none' }}>
          {save}
        </Button>
      </Box>
    </Box>
  );
}

export default function MoveActionSheet({
  open, view, title, actions, onAction, onClose,
  nags, onNagToggle, nagLabels, comment, onCommentSave, labels,
}: MoveActionSheetProps) {
  return (
    <Drawer
      anchor="bottom"
      open={open}
      onClose={onClose}
      slotProps={{
        paper: {
          sx: {
            borderTopLeftRadius: 16,
            borderTopRightRadius: 16,
            maxHeight: '80vh',
            pb: 'calc(12px + env(safe-area-inset-bottom))',
          },
        },
      }}
    >
      <Box data-testid="move-action-sheet" sx={{ pt: 1, px: 1 }}>
        <Box sx={{ width: 36, height: 4, borderRadius: 2, bgcolor: 'divider', mx: 'auto', mb: 1 }} />
        <Typography sx={{ px: 1, pb: 1, fontFamily: 'monospace', fontSize: 14, fontWeight: 700, color: 'text.secondary' }}>
          {title}
        </Typography>

        {view === 'actions' && (
          <Box role="menu" sx={{ display: 'flex', flexDirection: 'column' }}>
            {actions.map(action => (
              <ButtonBase
                key={action.key}
                role="menuitem"
                onClick={() => onAction(action.key)}
                sx={{
                  justifyContent: 'flex-start',
                  gap: 2,
                  minHeight: 52,
                  px: 1.5,
                  borderRadius: 2,
                  fontSize: 16,
                  color: action.key === 'deleteMove' ? 'error.main' : 'text.primary',
                  '&:hover, &.Mui-focusVisible': { bgcolor: 'action.hover' },
                }}
              >
                <Box component="span" sx={{ display: 'flex', width: 24, justifyContent: 'center', color: action.color }}>
                  {action.icon}
                </Box>
                {action.label}
              </ButtonBase>
            ))}
          </Box>
        )}

        {view === 'nags' && onNagToggle && (
          <Box sx={{ '& [data-testid^="nag-chip-"]': { minWidth: 40, height: 40, fontSize: 16 } }}>
            <NagPalette nags={nags} onToggle={onNagToggle} labels={nagLabels ?? {}} />
          </Box>
        )}

        {view === 'comment' && (
          <CommentForm
            initial={comment}
            placeholder={labels.commentPlaceholder}
            save={labels.save}
            cancel={labels.cancel}
            onSave={onCommentSave}
            onCancel={onClose}
          />
        )}
      </Box>
    </Drawer>
  );
}
