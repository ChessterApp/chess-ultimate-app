/* Hallmark · component: pill-row · genre: modern-minimal · theme: project (reuses existing page tokens)
 * states: default · hover · focus · active · editing · error
 * contrast: pass — reuses the page's existing stone/light pill palette, no new colors
 *
 * Variation B database switcher for the Database page header. Replaces the single
 * static "Master Database" badge with a horizontal, wrap-friendly row of pills:
 * a read-only locked Master pill (TWIC count), one pill per user database with
 * inline rename, and a "+ New" pill that opens an inline input. Every colour and
 * radius is lifted verbatim from the page's existing tab chips — no novelty.
 */

'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { Box, Typography, InputBase, Popover, Button } from '@mui/material';
import { FolderOpen, Add, Edit, DeleteOutline, Restore } from '@mui/icons-material';
import { useDatabases, type UserDatabase, type DeletedDatabase } from '@/hooks/useDatabases';
import ConfirmDialog from '@/components/ui/ConfirmDialog';

interface DatabasePillRowProps {
  /** TWIC master count from /api/opponent/status (null until loaded). */
  masterGameCount: number | null;
  /** Currently active database id, or null for the Master pill. */
  selectedDatabaseId: string | null;
  /** Fires with a database id (scopes the games list) or null (Master view). */
  onSelect: (databaseId: string | null) => void;
}

// Shared pill geometry/colour — identical to the existing tab chips on the page.
const pillSx = (active: boolean) => ({
  display: 'inline-flex',
  alignItems: 'center',
  gap: 0.5,
  height: 28,
  px: 1.25,
  borderRadius: '9999px',
  fontSize: 12,
  fontWeight: 600,
  lineHeight: 1,
  bgcolor: active ? 'primary.main' : 'rgba(255,255,255,0.95)',
  color: active ? '#fff' : 'var(--text-secondary)',
  border: active ? 'none' : '1px solid rgba(31,41,55,0.1)',
  cursor: 'pointer',
  flexShrink: 0,
  transition: 'background-color 0.15s',
  '&:hover': { bgcolor: active ? 'primary.dark' : 'var(--surface-card-hover)' },
  '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main', outlineOffset: 2 },
});

const countSx = (active: boolean) => ({
  fontWeight: 700,
  fontSize: 11,
  color: active ? 'rgba(255,255,255,0.75)' : 'var(--text-tertiary)',
});

export default function DatabasePillRow({ masterGameCount, selectedDatabaseId, onSelect }: DatabasePillRowProps) {
  const { databases, error, refresh, createDatabase, renameDatabase, deleteDatabase, restoreDatabase, listDeleted } = useDatabases();

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState('');
  const [creating, setCreating] = useState(false);
  const [newValue, setNewValue] = useState('');
  const newInputRef = useRef<HTMLInputElement>(null);

  // ─── Delete confirmation + recently-deleted/restore panel ───
  const [deleteTarget, setDeleteTarget] = useState<UserDatabase | null>(null);
  const [deleted, setDeleted] = useState<DeletedDatabase[]>([]);
  const [restoreAnchor, setRestoreAnchor] = useState<HTMLElement | null>(null);

  const reloadDeleted = useCallback(async () => {
    setDeleted(await listDeleted());
  }, [listDeleted]);

  useEffect(() => {
    refresh();
    listDeleted().then(setDeleted);
  }, [refresh, listDeleted]);

  // ─── Rename ───
  const beginRename = useCallback((db: UserDatabase) => {
    setCreating(false);
    setEditingId(db.id);
    setEditingValue(db.name);
  }, []);

  const commitRename = useCallback(async (id: string) => {
    const name = editingValue.trim();
    const current = databases.find(d => d.id === id);
    if (!name || name === current?.name) {
      setEditingId(null);
      return;
    }
    const updated = await renameDatabase(id, name);
    if (updated) setEditingId(null); // keep the input open on 409/error
  }, [editingValue, databases, renameDatabase]);

  // ─── Create ───
  const beginCreate = useCallback(() => {
    setEditingId(null);
    setCreating(true);
    setNewValue('');
  }, []);

  useEffect(() => {
    if (creating) newInputRef.current?.focus();
  }, [creating]);

  const commitCreate = useCallback(async () => {
    const name = newValue.trim();
    if (!name) return; // keep input open; empty is a no-op
    const created = await createDatabase(name);
    if (created) {
      setCreating(false);
      setNewValue('');
      onSelect(created.id);
    }
    // 409/error → input stays open, hook `error` is shown inline
  }, [newValue, createDatabase, onSelect]);

  const cancelCreate = useCallback(() => {
    setCreating(false);
    setNewValue('');
  }, []);

  // ─── Delete (soft) ───
  const confirmDelete = useCallback(async () => {
    if (!deleteTarget) return;
    const { id } = deleteTarget;
    const wasActive = selectedDatabaseId === id;
    setDeleteTarget(null);
    const ok = await deleteDatabase(id);
    if (ok) {
      // If the removed db was active, fall back to the default db (else Master).
      if (wasActive) {
        const fallback = databases.find(db => db.is_default && db.id !== id);
        onSelect(fallback ? fallback.id : null);
      }
      reloadDeleted();
    }
  }, [deleteTarget, selectedDatabaseId, deleteDatabase, databases, onSelect, reloadDeleted]);

  // ─── Restore ───
  const handleRestore = useCallback(async (id: string) => {
    const restored = await restoreDatabase(id);
    if (restored) {
      await reloadDeleted();
      onSelect(restored.id);
    }
  }, [restoreDatabase, reloadDeleted, onSelect]);

  const masterActive = selectedDatabaseId === null;

  return (
    <Box>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 0.5 }}>
        {/* Master — read-only, selectable, default-active on load */}
        <Box
          component="button"
          type="button"
          onClick={() => onSelect(null)}
          aria-pressed={masterActive}
          sx={{ ...pillSx(masterActive), fontFamily: 'inherit', appearance: 'none' }}
        >
          <span aria-hidden style={{ fontSize: 13, lineHeight: 1 }}>📖</span>
          <span>Master</span>
          {masterGameCount !== null && (
            <Typography component="span" sx={countSx(masterActive)}>
              {masterGameCount.toLocaleString()}
            </Typography>
          )}
        </Box>

        {/* One pill per user database */}
        {databases.map((db) => {
          const active = selectedDatabaseId === db.id;
          const isEditing = editingId === db.id;
          if (isEditing) {
            return (
              <Box key={db.id} sx={{ ...pillSx(active), cursor: 'text' }}>
                <InputBase
                  autoFocus
                  value={editingValue}
                  onChange={(e) => setEditingValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') { e.preventDefault(); commitRename(db.id); }
                    else if (e.key === 'Escape') { e.preventDefault(); setEditingId(null); }
                  }}
                  onBlur={() => setEditingId(null)}
                  inputProps={{ 'aria-label': 'Rename database', maxLength: 80, size: Math.max(6, editingValue.length) }}
                  sx={{ fontSize: 12, fontWeight: 600, color: 'inherit', p: 0, '& input': { p: 0 } }}
                />
              </Box>
            );
          }
          return (
            <Box
              key={db.id}
              role="button"
              tabIndex={0}
              aria-pressed={active}
              onClick={() => onSelect(db.id)}
              onDoubleClick={() => beginRename(db)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(db.id); }
              }}
              sx={{
                ...pillSx(active),
                '&:hover .db-action': { opacity: 1 },
                '& .db-action': { opacity: active ? 1 : 0 },
              }}
            >
              {db.is_default && <FolderOpen sx={{ fontSize: 13 }} />}
              <span>{db.name}</span>
              <Typography component="span" sx={countSx(active)}>{db.game_count}</Typography>
              <Box
                component="span"
                role="button"
                tabIndex={0}
                aria-label={`Rename ${db.name}`}
                className="db-action"
                onClick={(e) => { e.stopPropagation(); beginRename(db); }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') { e.stopPropagation(); e.preventDefault(); beginRename(db); }
                }}
                sx={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  ml: 0.25,
                  transition: 'opacity 0.15s',
                  '&:focus-visible': { outline: '2px solid', outlineColor: active ? '#fff' : 'primary.main', outlineOffset: 1, borderRadius: '4px' },
                }}
              >
                <Edit sx={{ fontSize: 13 }} />
              </Box>
              {/* Delete — hidden for the built-in default "My Games" db (backend also guards). */}
              {!db.is_default && (
                <Box
                  component="span"
                  role="button"
                  tabIndex={0}
                  aria-label={`Delete ${db.name}`}
                  className="db-action"
                  onClick={(e) => { e.stopPropagation(); setDeleteTarget(db); }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') { e.stopPropagation(); e.preventDefault(); setDeleteTarget(db); }
                  }}
                  sx={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    transition: 'opacity 0.15s',
                    '&:hover': { color: active ? '#fff' : 'error.main' },
                    '&:focus-visible': { outline: '2px solid', outlineColor: active ? '#fff' : 'error.main', outlineOffset: 1, borderRadius: '4px' },
                  }}
                >
                  <DeleteOutline sx={{ fontSize: 13 }} />
                </Box>
              )}
            </Box>
          );
        })}

        {/* + New — opens an inline input in place */}
        {creating ? (
          <Box sx={{ ...pillSx(false), cursor: 'text' }}>
            <Add sx={{ fontSize: 14 }} />
            <InputBase
              inputRef={newInputRef}
              placeholder="Name…"
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); commitCreate(); }
                else if (e.key === 'Escape') { e.preventDefault(); cancelCreate(); }
              }}
              onBlur={cancelCreate}
              inputProps={{ 'aria-label': 'New database name', maxLength: 80, size: Math.max(6, newValue.length) }}
              sx={{ fontSize: 12, fontWeight: 600, color: 'inherit', p: 0, '& input': { p: 0 } }}
            />
          </Box>
        ) : (
          <Box
            component="button"
            type="button"
            onClick={beginCreate}
            aria-label="New database"
            sx={{ ...pillSx(false), fontFamily: 'inherit', appearance: 'none', color: 'var(--text-tertiary)' }}
          >
            <Add sx={{ fontSize: 14 }} />
            <span>New</span>
          </Box>
        )}

        {/* Recently deleted — only when there's something to restore */}
        {deleted.length > 0 && (
          <Box
            component="button"
            type="button"
            onClick={(e) => setRestoreAnchor(e.currentTarget)}
            aria-label={`Recently deleted (${deleted.length})`}
            sx={{
              ...pillSx(false),
              fontFamily: 'inherit',
              appearance: 'none',
              color: 'var(--text-tertiary)',
              bgcolor: 'transparent',
              border: 'none',
            }}
          >
            <Restore sx={{ fontSize: 14 }} />
            <span>Recently deleted</span>
            <Typography component="span" sx={countSx(false)}>{deleted.length}</Typography>
          </Box>
        )}
      </Box>

      {/* Inline error (duplicate name / validation) — never throws, keeps input open */}
      {error && (creating || editingId) && (
        <Typography variant="caption" sx={{ display: 'block', mt: 0.5, color: 'error.main', fontSize: 11 }}>
          {error}
        </Typography>
      )}

      {/* Restore panel — lists soft-deleted dbs with their remaining recovery window */}
      <Popover
        open={Boolean(restoreAnchor)}
        anchorEl={restoreAnchor}
        onClose={() => setRestoreAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
        transformOrigin={{ vertical: 'top', horizontal: 'left' }}
        slotProps={{ paper: { sx: { p: 1, minWidth: 240, maxWidth: 300 } } }}
      >
        <Typography sx={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', px: 0.5, pb: 0.5 }}>
          Recently deleted
        </Typography>
        {deleted.map((d) => (
          <Box
            key={d.id}
            sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.5, px: 0.5 }}
          >
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography sx={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {d.name}
              </Typography>
              <Typography sx={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                {d.game_count} games · {d.days_left} days left
              </Typography>
            </Box>
            <Button
              size="small"
              startIcon={<Restore sx={{ fontSize: 14 }} />}
              onClick={() => handleRestore(d.id)}
              sx={{ fontSize: 11, textTransform: 'none', flexShrink: 0 }}
            >
              Restore
            </Button>
          </Box>
        ))}
      </Popover>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        variant="danger"
        title="Delete database"
        message={deleteTarget ? `Delete '${deleteTarget.name}'? Its ${deleteTarget.game_count} games will be recoverable for 30 days.` : ''}
        confirmText="Delete"
        cancelText="Cancel"
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </Box>
  );
}
