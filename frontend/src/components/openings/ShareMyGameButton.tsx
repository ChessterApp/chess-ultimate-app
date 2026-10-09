'use client';

/**
 * ShareMyGameButton — share control for a user's OWN saved game.
 *
 * Unlike the master-database `ShareGameButton` (opaque slug, no server state),
 * sharing a saved game mints a revocable token server-side. The menu exposes
 * both actions:
 *   • "Copy share link" → POST /api/games/<id>/share (idempotent) → share/copy
 *     a `https://chesster.io/g/u/<token>` link.
 *   • "Disable link"    → DELETE /api/games/<id>/share → revokes the token.
 *
 * Share/copy itself reuses `shareOrCopyGame` from ShareGameButton.
 */
import React, { useCallback, useState } from 'react';
import {
  IconButton, Tooltip, Menu, MenuItem, ListItemIcon, ListItemText, Snackbar, Alert,
} from '@mui/material';
import { IosShare, LinkOff } from '@mui/icons-material';
import { useAuth } from '@clerk/nextjs';
import { useTranslations } from 'next-intl';
import { apiFetch } from '@/lib/api';
import { shareOrCopyGame } from './ShareGameButton';

/** Build the shareable `/g/u/<token>` short link for an owned game. */
export function buildMyGameShareUrl(origin: string, token: string): string {
  return `${origin}/g/u/${token}`;
}

interface ShareMyGameButtonProps {
  gameId: string;
  white?: string;
  black?: string;
  /** Extra sx merged onto the IconButton (e.g. hover-reveal on list rows). */
  sx?: object;
  size?: 'small' | 'medium';
}

export default function ShareMyGameButton({
  gameId, white, black, sx, size = 'small',
}: ShareMyGameButtonProps) {
  const t = useTranslations('debut.shareGame');
  const { getToken } = useAuth();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [toast, setToast] = useState<{ open: boolean; msg: string; severity: 'success' | 'error' }>(
    { open: false, msg: '', severity: 'success' }
  );

  const authedShareFetch = useCallback(async <T,>(method: 'POST' | 'DELETE'): Promise<T> => {
    const token = await getToken();
    if (!token) throw new Error('Not authenticated');
    const apiBase = process.env.NEXT_PUBLIC_API_URL || '';
    return apiFetch<T>(`${apiBase}/api/games/${gameId}/share`, {
      method,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    });
  }, [getToken, gameId]);

  const openMenu = useCallback((e: React.MouseEvent<HTMLElement>) => {
    e.stopPropagation(); // never trigger the row's open-game handler
    setAnchorEl(e.currentTarget);
  }, []);

  const handleShare = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    setAnchorEl(null);
    try {
      const { share_token } = await authedShareFetch<{ share_token: string }>('POST');
      const url = buildMyGameShareUrl(window.location.origin, share_token);
      const names = white && black ? `${white} vs ${black}` : 'Chess game';
      const method = await shareOrCopyGame({ url, title: `${names} · Chesster` });
      if (method === 'clipboard') {
        setToast({ open: true, msg: t('linkCopied'), severity: 'success' });
      }
    } catch (err: unknown) {
      // User-cancelled native share is not an error.
      if (err instanceof Error && err.name === 'AbortError') return;
      setToast({ open: true, msg: t('shareFailed'), severity: 'error' });
    }
  }, [authedShareFetch, white, black, t]);

  const handleDisable = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    setAnchorEl(null);
    try {
      await authedShareFetch<unknown>('DELETE');
      setToast({ open: true, msg: t('linkDisabled'), severity: 'success' });
    } catch {
      setToast({ open: true, msg: t('disableFailed'), severity: 'error' });
    }
  }, [authedShareFetch, t]);

  return (
    <>
      <Tooltip title={t('myGameShareTooltip')}>
        <IconButton
          size={size}
          onClick={openMenu}
          aria-label={t('myGameShareTooltip')}
          sx={{ p: 0.5, color: 'text.secondary', ...sx }}
        >
          <IosShare sx={{ fontSize: 16 }} />
        </IconButton>
      </Tooltip>
      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={() => setAnchorEl(null)}
        onClick={(e) => e.stopPropagation()}
      >
        <MenuItem onClick={handleShare}>
          <ListItemIcon><IosShare fontSize="small" /></ListItemIcon>
          <ListItemText>{t('copyShareLink')}</ListItemText>
        </MenuItem>
        <MenuItem onClick={handleDisable}>
          <ListItemIcon><LinkOff fontSize="small" /></ListItemIcon>
          <ListItemText>{t('disableLink')}</ListItemText>
        </MenuItem>
      </Menu>
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
