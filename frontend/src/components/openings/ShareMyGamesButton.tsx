'use client';

/**
 * ShareMyGamesButton — owner-facing "Share database" control for the database
 * currently selected in My Games.
 *
 * Uses the per-database share link (`/database?sdb=<token>`): the recipient
 * opens it read-only (Games + Analysis) and can copy the whole database into
 * their own workspace.
 *   • Open  → POST /api/databases/<id>/share (idempotent) → mint/return token.
 *   • Copy  → copies the link (via shareOrCopyGame).
 *   • Revoke→ DELETE /api/databases/<id>/share → link disabled; offer regen.
 *
 * MyGamesPanel only renders it in owner mode with a single database selected
 * (keyed by id, so switching databases starts from a clean state);
 * the default database can't be shared, so it renders nothing for that one.
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Button, Popover, Box, Typography, TextField, CircularProgress, Snackbar, Alert,
} from '@mui/material';
import { IosShare, ContentCopy, LinkOff, Refresh } from '@mui/icons-material';
import { useTranslations } from 'next-intl';
import { useDatabases } from '@/hooks/useDatabases';
import { shareOrCopyGame } from './ShareGameButton';
import { buildDatabaseShareUrl } from './DatabasePillRow';

interface ShareMyGamesButtonProps {
  databaseId: string;
}

export default function ShareMyGamesButton({ databaseId }: ShareMyGamesButtonProps) {
  const t = useTranslations('debut.myGames.shareAll');
  const { databases, refresh, shareDatabase, revokeShare } = useDatabases();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [revoked, setRevoked] = useState(false);
  const [toast, setToast] = useState<{ open: boolean; msg: string; severity: 'success' | 'error' }>(
    { open: false, msg: '', severity: 'success' }
  );

  // Name, default flag and any existing token come from the owner's db list.
  useEffect(() => {
    refresh();
  }, [refresh]);

  const database = databases.find(db => db.id === databaseId);
  const existingToken = database?.share_token;
  const dbName = database?.name;

  const mint = useCallback(async () => {
    setLoading(true);
    setError(false);
    const minted = await shareDatabase(databaseId);
    if (minted) {
      setToken(minted);
      setRevoked(false);
    } else {
      setError(true);
    }
    setLoading(false);
  }, [databaseId, shareDatabase]);

  const handleOpen = useCallback((e: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(e.currentTarget);
    if (token) return;
    if (existingToken) setToken(existingToken);
    else mint();
  }, [token, existingToken, mint]);

  const handleCopy = useCallback(async () => {
    if (!token) return;
    const url = buildDatabaseShareUrl(window.location.origin, token);
    try {
      const method = await shareOrCopyGame({ url, title: `${dbName ?? t('title')} · Chesster` });
      if (method === 'clipboard') {
        setToast({ open: true, msg: t('copied'), severity: 'success' });
      }
    } catch (err: unknown) {
      // User-cancelled native share is not an error.
      if (err instanceof Error && err.name === 'AbortError') return;
      setToast({ open: true, msg: t('error'), severity: 'error' });
    }
  }, [token, dbName, t]);

  const handleRevoke = useCallback(async () => {
    setLoading(true);
    setError(false);
    if (await revokeShare(databaseId)) {
      setToken(null);
      setRevoked(true);
    } else {
      setError(true);
    }
    setLoading(false);
  }, [databaseId, revokeShare]);

  if (database?.is_default) return null;

  const shareUrl = token
    ? buildDatabaseShareUrl(typeof window !== 'undefined' ? window.location.origin : '', token)
    : '';

  return (
    <>
      <Button
        variant="outlined"
        size="small"
        startIcon={<IosShare sx={{ fontSize: 16 }} />}
        onClick={handleOpen}
        sx={{
          height: 40,
          flexShrink: 0,
          fontSize: 12,
          textTransform: 'none',
          whiteSpace: 'nowrap',
          color: 'text.secondary',
          borderColor: 'rgba(255,255,255,0.15)',
          '&:hover': { borderColor: 'rgba(255,255,255,0.3)', bgcolor: 'rgba(255,255,255,0.04)' },
        }}
      >
        {t('button')}
      </Button>

      <Popover
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <Box sx={{ p: 2, width: 300, maxWidth: 'calc(100vw - 32px)', display: 'flex', flexDirection: 'column', gap: 1.25 }}>
          <Box>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: 14 }}>
              {t('title')}
            </Typography>
            {dbName && (
              <Typography variant="body2" sx={{ fontSize: 13, color: 'text.primary', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {dbName}
              </Typography>
            )}
          </Box>

          {loading && (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
              <CircularProgress size={24} />
            </Box>
          )}

          {!loading && error && (
            <>
              <Typography variant="body2" sx={{ color: 'error.main', fontSize: 13 }}>
                {t('error')}
              </Typography>
              <Button
                size="small"
                startIcon={<Refresh sx={{ fontSize: 16 }} />}
                onClick={mint}
                sx={{ textTransform: 'none', fontSize: 12, alignSelf: 'flex-start' }}
              >
                {t('regenerate')}
              </Button>
            </>
          )}

          {!loading && !error && !token && revoked && (
            <>
              <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: 13 }}>
                {t('revoked')}
              </Typography>
              <Button
                size="small"
                startIcon={<Refresh sx={{ fontSize: 16 }} />}
                onClick={mint}
                sx={{ textTransform: 'none', fontSize: 12, alignSelf: 'flex-start' }}
              >
                {t('regenerate')}
              </Button>
            </>
          )}

          {!loading && !error && token && (
            <>
              <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: 12 }}>
                {t('description')}
              </Typography>
              <TextField
                value={shareUrl}
                size="small"
                fullWidth
                slotProps={{ input: { readOnly: true } }}
                sx={{ '& .MuiOutlinedInput-root': { fontSize: 12 } }}
              />
              <Box sx={{ display: 'flex', gap: 1 }}>
                <Button
                  size="small"
                  variant="contained"
                  startIcon={<ContentCopy sx={{ fontSize: 16 }} />}
                  onClick={handleCopy}
                  sx={{ textTransform: 'none', fontSize: 12, flex: 1 }}
                >
                  {t('copy')}
                </Button>
                <Button
                  size="small"
                  color="error"
                  startIcon={<LinkOff sx={{ fontSize: 16 }} />}
                  onClick={handleRevoke}
                  sx={{ textTransform: 'none', fontSize: 12 }}
                >
                  {t('revoke')}
                </Button>
              </Box>
            </>
          )}
        </Box>
      </Popover>

      <Snackbar
        open={toast.open}
        autoHideDuration={2500}
        onClose={() => setToast(prev => ({ ...prev, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={toast.severity} variant="filled" sx={{ fontSize: 13 }}>
          {toast.msg}
        </Alert>
      </Snackbar>
    </>
  );
}
