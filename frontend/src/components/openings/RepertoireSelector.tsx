'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Box, Select, MenuItem, IconButton, Button, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, ToggleButton, ToggleButtonGroup,
  Typography, Chip, Menu, ListItemIcon, ListItemText,
} from '@mui/material';
import {
  Add as AddIcon, MoreVert, Edit, Delete, FileDownload, FileUpload,
} from '@mui/icons-material';
import type { Repertoire } from '@/hooks/useOpeningRepertoire';

interface RepertoireSelectorProps {
  repertoires: Repertoire[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCreate: (name: string, color: 'w' | 'b') => Promise<void>;
  onRename: (id: string, name: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onImportPgn: () => void;
  onExportPgn: () => void;
  loading: boolean;
}

export default function RepertoireSelector({
  repertoires, selectedId, onSelect, onCreate, onRename, onDelete,
  onImportPgn, onExportPgn, loading,
}: RepertoireSelectorProps) {
  const t = useTranslations('debut');
  const [createOpen, setCreateOpen] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newColor, setNewColor] = useState<'w' | 'b'>('w');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);

  const selected = repertoires.find(r => r.id === selectedId);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    await onCreate(newName.trim(), newColor);
    setCreateOpen(false);
    setNewName('');
  };

  const handleRename = async () => {
    if (!editingId || !newName.trim()) return;
    await onRename(editingId, newName.trim());
    setRenameOpen(false);
    setNewName('');
    setEditingId(null);
  };

  const handleDelete = async () => {
    if (!editingId) return;
    await onDelete(editingId);
    setDeleteOpen(false);
    setEditingId(null);
  };

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: 1, borderBottom: '1px solid #333' }}>
      <Select
        value={selectedId || ''}
        onChange={(e) => onSelect(e.target.value)}
        size="small"
        sx={{
          flex: 1, color: '#e0e0e0', bgcolor: '#2a2a2a',
          '.MuiOutlinedInput-notchedOutline': { borderColor: '#444' },
          '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#666' },
          '.MuiSvgIcon-root': { color: '#aaa' },
        }}
        displayEmpty
        renderValue={(val) => {
          if (!val) return <em style={{ color: '#888' }}>Select repertoire...</em>;
          const rep = repertoires.find(r => r.id === val);
          if (!rep) return val;
          return (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <span>{rep.color === 'w' ? '♔' : '♚'}</span>
              <span>{rep.name}</span>
              {rep.node_count !== undefined && (
                <Chip label={rep.node_count} size="small" sx={{ height: 18, fontSize: 11, bgcolor: '#444', color: '#ccc' }} />
              )}
            </Box>
          );
        }}
      >
        {repertoires.map((rep) => (
          <MenuItem key={rep.id} value={rep.id}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
              <span>{rep.color === 'w' ? '♔' : '♚'}</span>
              <span>{rep.name}</span>
              {rep.node_count !== undefined && (
                <Chip label={rep.node_count} size="small" sx={{ ml: 'auto', height: 18, fontSize: 11 }} />
              )}
            </Box>
          </MenuItem>
        ))}
      </Select>

      <IconButton size="small" onClick={() => { setNewName(''); setNewColor('w'); setCreateOpen(true); }} sx={{ color: '#aaa' }}>
        <AddIcon />
      </IconButton>

      <IconButton
        size="small"
        onClick={(e) => setMenuAnchor(e.currentTarget)}
        disabled={!selectedId}
        sx={{ color: '#aaa' }}
      >
        <MoreVert />
      </IconButton>

      {/* Kebab Menu */}
      <Menu anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={() => setMenuAnchor(null)}>
        <MenuItem onClick={() => {
          setEditingId(selectedId);
          setNewName(selected?.name || '');
          setRenameOpen(true);
          setMenuAnchor(null);
        }}>
          <ListItemIcon><Edit fontSize="small" /></ListItemIcon>
          <ListItemText>{t('rename')}</ListItemText>
        </MenuItem>
        <MenuItem onClick={() => { onImportPgn(); setMenuAnchor(null); }}>
          <ListItemIcon><FileUpload fontSize="small" /></ListItemIcon>
          <ListItemText>{t('importPgn')}</ListItemText>
        </MenuItem>
        <MenuItem onClick={() => { onExportPgn(); setMenuAnchor(null); }}>
          <ListItemIcon><FileDownload fontSize="small" /></ListItemIcon>
          <ListItemText>{t('exportPgn')}</ListItemText>
        </MenuItem>
        <MenuItem onClick={() => {
          setEditingId(selectedId);
          setDeleteOpen(true);
          setMenuAnchor(null);
        }} sx={{ color: '#f44336' }}>
          <ListItemIcon><Delete fontSize="small" sx={{ color: '#f44336' }} /></ListItemIcon>
          <ListItemText>{t('delete')}</ListItemText>
        </MenuItem>
      </Menu>

      {/* Create Dialog */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} PaperProps={{ sx: { bgcolor: '#2a2a2a', color: '#e0e0e0' } }}>
        <DialogTitle>{t('newRepertoire')}</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '8px !important', minWidth: 300 }}>
          <TextField
            autoFocus
            label={t('name')}
            value={newName}
            onChange={e => setNewName(e.target.value)}
            size="small"
            fullWidth
            onKeyDown={e => e.key === 'Enter' && handleCreate()}
            InputLabelProps={{ sx: { color: '#aaa' } }}
            InputProps={{ sx: { color: '#e0e0e0' } }}
          />
          <ToggleButtonGroup
            value={newColor}
            exclusive
            onChange={(_, v) => v && setNewColor(v)}
            size="small"
          >
            <ToggleButton value="w" sx={{ color: '#e0e0e0' }}>{`♔ ${t('white')}`}</ToggleButton>
            <ToggleButton value="b" sx={{ color: '#e0e0e0' }}>{`♚ ${t('black')}`}</ToggleButton>
          </ToggleButtonGroup>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)} sx={{ color: '#aaa' }}>{t('cancel')}</Button>
          <Button onClick={handleCreate} variant="contained" disabled={!newName.trim()}>{t('create')}</Button>
        </DialogActions>
      </Dialog>

      {/* Rename Dialog */}
      <Dialog open={renameOpen} onClose={() => setRenameOpen(false)} PaperProps={{ sx: { bgcolor: '#2a2a2a', color: '#e0e0e0' } }}>
        <DialogTitle>{t('renameRepertoire')}</DialogTitle>
        <DialogContent sx={{ pt: '8px !important', minWidth: 300 }}>
          <TextField
            autoFocus
            label={t('name')}
            value={newName}
            onChange={e => setNewName(e.target.value)}
            size="small"
            fullWidth
            onKeyDown={e => e.key === 'Enter' && handleRename()}
            InputLabelProps={{ sx: { color: '#aaa' } }}
            InputProps={{ sx: { color: '#e0e0e0' } }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRenameOpen(false)} sx={{ color: '#aaa' }}>{t('cancel')}</Button>
          <Button onClick={handleRename} variant="contained" disabled={!newName.trim()}>{t('rename')}</Button>
        </DialogActions>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onClose={() => setDeleteOpen(false)} PaperProps={{ sx: { bgcolor: '#2a2a2a', color: '#e0e0e0' } }}>
        <DialogTitle>{t('deleteRepertoireTitle')}</DialogTitle>
        <DialogContent>
          <Typography>{t('deleteRepertoireConfirm')}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteOpen(false)} sx={{ color: '#aaa' }}>{t('cancel')}</Button>
          <Button onClick={handleDelete} color="error" variant="contained">{t('delete')}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
