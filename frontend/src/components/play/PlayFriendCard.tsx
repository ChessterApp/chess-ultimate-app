'use client';

/**
 * "Play a friend" entry (phase 3). Pick a time control + colour, create a
 * challenge via POST /api/games/challenge, copy the invite link, and navigate
 * the creator to the live-game lobby. Rendered by the play page only when
 * ONLINE_PLAY_ENABLED is on (the flag gate lives at the call site).
 */

import React, { useState } from 'react';
import { Box, Button, Typography, ToggleButton, ToggleButtonGroup } from '@mui/material';
import { useRouter } from 'next/navigation';
import type { ColorChoice } from '@/lib/live-game/types';

interface TimeControl {
  key: string;
  label: string;
  initialSec: number | null;
  incrementSec: number | null;
}

const TIME_CONTROLS: TimeControl[] = [
  { key: '3+2', label: '3 + 2', initialSec: 180, incrementSec: 2 },
  { key: '5+0', label: '5 + 0', initialSec: 300, incrementSec: 0 },
  { key: '10+0', label: '10 + 0', initialSec: 600, incrementSec: 0 },
  { key: 'untimed', label: 'Untimed', initialSec: null, incrementSec: null },
];

const COLORS: Array<{ key: ColorChoice; label: string }> = [
  { key: 'white', label: 'White' },
  { key: 'random', label: 'Random' },
  { key: 'black', label: 'Black' },
];

export default function PlayFriendCard() {
  const router = useRouter();
  const [tcKey, setTcKey] = useState('5+0');
  const [color, setColor] = useState<ColorChoice>('random');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createChallenge = async () => {
    if (creating) return;
    setCreating(true);
    setError(null);
    const tc = TIME_CONTROLS.find((t) => t.key === tcKey) ?? TIME_CONTROLS[1];
    try {
      const res = await fetch('/api/games/challenge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          colorChoice: color,
          initialSec: tc.initialSec,
          incrementSec: tc.incrementSec,
        }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        setError(body.error || 'Could not create the game. Try again.');
        setCreating(false);
        return;
      }
      const { gameId, url } = (await res.json()) as { gameId: string; url: string };
      // Best-effort copy the invite link; navigation is what matters.
      try {
        await navigator.clipboard?.writeText(url);
      } catch {
        /* clipboard may be unavailable (permissions / non-secure ctx) */
      }
      router.push(`/play/live/${gameId}`);
    } catch {
      setError('Network error. Try again.');
      setCreating(false);
    }
  };

  return (
    <Box
      data-testid="play-friend-card"
      sx={{
        mt: 3,
        p: { xs: 2, sm: 3 },
        borderRadius: '20px',
        bgcolor: '#FFFFFF',
        border: '1px solid #E3EAF6',
        boxShadow: '0 8px 24px rgba(30,60,120,0.08)',
      }}
    >
      <Typography variant="h6" sx={{ fontWeight: 800, color: '#1E2A44', mb: 0.5 }}>
        Play a friend
      </Typography>
      <Typography variant="body2" sx={{ color: '#5C6B85', mb: 2 }}>
        Create a game and share the link — it opens live for both of you.
      </Typography>

      <Typography variant="caption" sx={{ display: 'block', fontWeight: 700, color: '#5C6B85', mb: 0.75 }}>
        TIME CONTROL
      </Typography>
      <ToggleButtonGroup
        value={tcKey}
        exclusive
        onChange={(_e, v) => v && setTcKey(v)}
        sx={{ flexWrap: 'wrap', gap: 1, mb: 2 }}
      >
        {TIME_CONTROLS.map((tc) => (
          <ToggleButton
            key={tc.key}
            value={tc.key}
            sx={{ borderRadius: '12px !important', border: '1px solid #E3EAF6 !important', px: 2 }}
          >
            {tc.label}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>

      <Typography variant="caption" sx={{ display: 'block', fontWeight: 700, color: '#5C6B85', mb: 0.75 }}>
        YOUR COLOR
      </Typography>
      <ToggleButtonGroup
        value={color}
        exclusive
        onChange={(_e, v) => v && setColor(v as ColorChoice)}
        sx={{ flexWrap: 'wrap', gap: 1, mb: 2 }}
      >
        {COLORS.map((c) => (
          <ToggleButton
            key={c.key}
            value={c.key}
            sx={{ borderRadius: '12px !important', border: '1px solid #E3EAF6 !important', px: 2 }}
          >
            {c.label}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>

      {error && (
        <Typography variant="body2" sx={{ color: '#C62828', mb: 1.5 }}>
          {error}
        </Typography>
      )}

      <Button
        variant="contained"
        fullWidth
        disabled={creating}
        onClick={createChallenge}
        data-testid="create-challenge"
        sx={{
          borderRadius: '999px',
          textTransform: 'none',
          fontWeight: 800,
          py: 1.25,
          bgcolor: '#2E6BFF',
          '&:hover': { bgcolor: '#2258db' },
        }}
      >
        {creating ? 'Creating…' : 'Create game link'}
      </Button>
    </Box>
  );
}
