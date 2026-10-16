'use client';

import React from 'react';
import { IconButton } from '@mui/material';
import { Pause, VolumeUp } from '@mui/icons-material';

/** The 🔊 play / pause toggle shown next to a move that has a voice note. */
export default function VoiceNoteButton({ playing, label, onClick }: { playing: boolean; label: string; onClick: () => void }) {
  return (
    <IconButton
      size="small"
      data-testid="move-voice-note"
      aria-label={label}
      aria-pressed={playing}
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      sx={{ p: '3px', alignSelf: 'center', color: playing ? 'primary.main' : 'text.secondary', '&:hover': { color: 'primary.main' } }}
    >
      {playing ? <Pause sx={{ fontSize: 14 }} /> : <VolumeUp sx={{ fontSize: 14 }} />}
    </IconButton>
  );
}
