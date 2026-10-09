'use client';

/**
 * ShareGameButton — icon-only control that shares a link to a specific
 * master-database game. The link carries only an opaque slug (see
 * `@/lib/gameSlug`), never the data-source name.
 *
 * On click: native share sheet when available (mobile), otherwise copy to
 * clipboard with a "Link copied" toast.
 */
import React, { useCallback, useState } from 'react';
import { IconButton, Tooltip, Snackbar, Alert } from '@mui/material';
import { IosShare } from '@mui/icons-material';
import { encodeGameSlug, type GameSource } from '@/lib/gameSlug';

/** Build the shareable `/g/<slug>` short link for a game. The `/g/` route
 * renders OG previews and bounces to `/database?g=<slug>`. */
export function buildGameShareUrl(origin: string, source: GameSource, gameId: number): string {
  return `${origin}/g/${encodeGameSlug(source, gameId)}`;
}

/**
 * Decide and perform the share: native share sheet when `navigator.share`
 * exists, otherwise copy to clipboard. Returns which path was taken.
 */
export async function shareOrCopyGame(opts: {
  url: string;
  title: string;
  nav?: Navigator;
}): Promise<'share' | 'clipboard'> {
  const nav = opts.nav ?? (typeof navigator !== 'undefined' ? navigator : undefined);
  if (nav && typeof nav.share === 'function') {
    await nav.share({ title: opts.title, url: opts.url });
    return 'share';
  }
  if (nav?.clipboard?.writeText) {
    await nav.clipboard.writeText(opts.url);
  }
  return 'clipboard';
}

interface ShareGameButtonProps {
  source: string;
  gameId: string | number;
  white?: string;
  black?: string;
  /** Extra sx merged onto the IconButton (e.g. hover-reveal on list rows). */
  sx?: object;
  size?: 'small' | 'medium';
}

export default function ShareGameButton({
  source, gameId, white, black, sx, size = 'small',
}: ShareGameButtonProps) {
  const [toast, setToast] = useState<{ open: boolean; msg: string; severity: 'success' | 'error' }>(
    { open: false, msg: '', severity: 'success' }
  );

  // Master TWIC game rows carry no explicit source — treat empty as 'twic'.
  const resolvedSource = source && source.length > 0 ? source : 'twic';
  const numericId = typeof gameId === 'number' ? gameId : Number(gameId);
  const supported =
    (resolvedSource === 'twic' || resolvedSource === 'lichess') &&
    Number.isInteger(numericId) && numericId >= 0;

  const handleClick = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation(); // never trigger the row's open-game handler
    if (!supported) return;
    const url = buildGameShareUrl(window.location.origin, resolvedSource as GameSource, numericId);
    const names = white && black ? `${white} vs ${black}` : 'Chess game';
    const title = `${names} · Chesster`;
    try {
      const method = await shareOrCopyGame({ url, title });
      if (method === 'clipboard') {
        setToast({ open: true, msg: 'Link copied', severity: 'success' });
      }
    } catch (err: any) {
      // User-cancelled native share is not an error.
      if (err?.name === 'AbortError') return;
      setToast({ open: true, msg: 'Could not share link', severity: 'error' });
    }
  }, [supported, resolvedSource, numericId, white, black]);

  if (!supported) return null;

  return (
    <>
      <Tooltip title="Share game">
        <IconButton
          size={size}
          onClick={handleClick}
          aria-label="Share game"
          sx={{ p: 0.5, color: 'text.secondary', ...sx }}
        >
          <IosShare sx={{ fontSize: 18 }} />
        </IconButton>
      </Tooltip>
      <Snackbar
        open={toast.open}
        autoHideDuration={2500}
        onClose={() => setToast(t => ({ ...t, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={toast.severity} variant="filled" sx={{ fontSize: 13 }}>
          {toast.msg}
        </Alert>
      </Snackbar>
    </>
  );
}
