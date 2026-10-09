'use client';

/**
 * ShareMyGamesButton — owner-facing control to share an entire My Games
 * collection via a single revocable link.
 *
 * Mirrors the single-game `ShareMyGameButton` pattern (mint / copy / revoke /
 * regenerate) but hits the COLLECTION endpoints and produces a `/g/c/<token>`
 * link:
 *   • Open  → POST /api/games/collection/share (idempotent) → mint/return token.
 *   • Copy  → copies the `https://<host>/g/c/<token>` link (via shareOrCopyGame).
 *   • Revoke→ DELETE /api/games/collection/share → link disabled; offer regen.
 *
 * Only rendered in owner mode — MyGamesPanel hides it in shared/read-only mode.
 */
import React, { useCallback, useState } from 'react';
import {
  Button, Popover, Box, Typography, TextField, CircularProgress, Snackbar, Alert,
} from '@mui/material';
import { IosShare, ContentCopy, LinkOff, Refresh } from '@mui/icons-material';
import { useAuth } from '@clerk/nextjs';
import { useTranslations } from 'next-intl';
import { apiFetch } from '@/lib/api';
import { shareOrCopyGame } from './ShareGameButton';

/** Build the shareable `/g/c/<token>` collection link. */
export function buildCollectionShareUrl(origin: string, token: string): string {
  return `${origin}/g/c/${token}`;
}

export default function ShareMyGamesButton() {
  const t = useTranslations('debut.myGames.shareAll');
  const { getToken } = useAuth();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [revoked, setRevoked] = useState(false);
  const [toast, setToast] = useState<{ open: boolean; msg: string; severity: 'success' | 'error' }>(
    { open: false, msg: '', severity: 'success' }
  );

  const authedShareFetch = useCallback(async <T,>(method: 'POST' | 'DELETE'): Promise<T> => {
    const clerkToken = await getToken();
    if (!clerkToken) throw new Error('Not authenticated');
    const apiBase = process.env.NEXT_PUBLIC_API_URL || '';
    return apiFetch<T>(`${apiBase}/api/games/collection/share`, {
      method,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${clerkToken}` },
    });
  }, [getToken]);

  const mint = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const { token: minted } = await authedShareFetch<{ token: string }>('POST');
      setToken(minted);
      setRevoked(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [authedShareFetch]);

  const handleOpen = useCallback((e: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(e.currentTarget);
    // Idempotent on the server — only mint if we don't already hold a token.
    if (!token) mint();
  }, [token, mint]);

  const handleCopy = useCallback(async () => {
    if (!token) return;
    const url = buildCollectionShareUrl(window.location.origin, token);
    try {
      const method = await shareOrCopyGame({ url, title: `${t('title')} · Chesster` });
      if (method === 'clipboard') {
        setToast({ open: true, msg: t('copied'), severity: 'success' });
      }
    } catch (err: unknown) {
      // User-cancelled native share is not an error.
      if (err instanceof Error && err.name === 'AbortError') return;
      setToast({ open: true, msg: t('error'), severity: 'error' });
    }
  }, [token, t]);

  const handleRevoke = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      await authedShareFetch<unknown>('DELETE');
      setToken(null);
      setRevoked(true);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [authedShareFetch]);

  const shareUrl = token
    ? buildCollectionShareUrl(typeof window !== 'undefined' ? window.location.origin : '', token)
    : '';

  return (
    <>
      <Button
        variant="outlined"
        size="small"
        startIcon={<IosShare sx={{ fontSize: 16 }} />}
        onClick={handleOpen}
        sx={{
          fontSize: 12,
          textTransform: 'none',
          py: 0.75,
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
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
      >
        <Box sx={{ p: 2, width: 300, display: 'flex', flexDirection: 'column', gap: 1.25 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: 14 }}>
            {t('title')}
          </Typography>

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
