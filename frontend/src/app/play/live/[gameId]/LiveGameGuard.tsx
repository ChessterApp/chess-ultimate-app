'use client';

/**
 * Client auth guard for `/play/live/*` (phase 6).
 *
 * On the apex host (chesster.io) the middleware already enforces Clerk sign-in
 * for live-game routes, so a signed-out visitor never reaches this component and
 * the guard is a no-op. On tenant hosts (school subdomains / custom domains) the
 * middleware runs in pass-through mode with no edge auth, so `/play/live/*` would
 * otherwise render for signed-out visitors and then break on the authed API
 * calls. Here we detect the signed-out state client-side and redirect to the apex
 * sign-in with a `redirect_url` back to the exact game URL — matching the UX the
 * apex host already gets from middleware. For signed-in users it renders its
 * children unchanged on both hosts.
 */

import React, { useEffect } from 'react';
import { useUser } from '@clerk/nextjs';
import { Box, Typography } from '@mui/material';
import { fredoka, nunito } from '@/lib/fonts';
import { LIVE_INK, LIVE_INK_SOFT } from '@/lib/livePlayTheme';

const APEX_HOSTS = new Set(['chesster.io', 'www.chesster.io', 'localhost', '127.0.0.1']);

/** Sign-in URL that returns to the current game URL post-auth. */
function signInUrl(): string {
  const { hostname, href } = window.location;
  // Clerk's sign-in is only registered on the apex; tenant hosts must bounce
  // there and come back. On the apex a relative path keeps the same origin.
  const base = APEX_HOSTS.has(hostname) ? '' : 'https://chesster.io';
  return `${base}/sign-in?redirect_url=${encodeURIComponent(href)}`;
}

export default function LiveGameGuard({ children }: { children: React.ReactNode }) {
  const { isLoaded, isSignedIn } = useUser();

  useEffect(() => {
    if (isLoaded && !isSignedIn) {
      window.location.assign(signInUrl());
    }
  }, [isLoaded, isSignedIn]);

  // Until Clerk confirms a signed-in user, hold on a quiet loading card rather
  // than mounting the game (which would fire authed API calls with no session).
  if (!isLoaded || !isSignedIn) {
    return (
      <Box
        data-testid="live-game-auth-loading"
        sx={{
          maxWidth: 520,
          mx: 'auto',
          p: { xs: 3, sm: 4 },
          textAlign: 'center',
          fontFamily: nunito.style.fontFamily,
        }}
      >
        <Typography
          component="p"
          sx={{
            fontFamily: fredoka.style.fontFamily,
            fontWeight: 700,
            fontSize: 20,
            color: LIVE_INK,
            mb: 1,
          }}
        >
          Loading game…
        </Typography>
        <Typography sx={{ color: LIVE_INK_SOFT }}>Checking your sign-in.</Typography>
      </Box>
    );
  }

  return <>{children}</>;
}
