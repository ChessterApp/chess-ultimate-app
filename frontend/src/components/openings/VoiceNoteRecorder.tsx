'use client';

/**
 * VoiceNoteRecorder — record a voice note for one move: tap to record, tap to
 * stop (auto-stops at 2:00), preview, then Save / Re-record / Cancel. Rendered
 * inside the mobile move sheet and the desktop voice-note dialog.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Box, Button, ButtonBase, CircularProgress, Typography } from '@mui/material';
import { Mic, Stop } from '@mui/icons-material';
import useVoiceRecorder, { type VoiceRecorderErrorCode, type VoiceRecording } from '@/hooks/useVoiceRecorder';
import { VOICE_NOTE_MAX_SEC, formatDuration } from '@/lib/voiceNotes';

export interface VoiceNoteRecorderLabels {
  record: string;
  stop: string;
  save: string;
  rerecord: string;
  cancel: string;
  saving: string;
  hint: string;
  micDenied: string;
  micUnavailable: string;
  saveFailed: string;
}

interface VoiceNoteRecorderProps {
  /** Resolves true once stored; false keeps the preview so the user can retry. */
  onSave: (recording: VoiceRecording) => Promise<boolean>;
  onCancel: () => void;
  labels: VoiceNoteRecorderLabels;
}

export default function VoiceNoteRecorder({ onSave, onCancel, labels }: VoiceNoteRecorderProps) {
  const [recording, setRecording] = useState<VoiceRecording | null>(null);
  const [errorCode, setErrorCode] = useState<VoiceRecorderErrorCode | 'save' | null>(null);
  const [saving, setSaving] = useState(false);

  const recorder = useVoiceRecorder({
    maxDurationSec: VOICE_NOTE_MAX_SEC,
    onRecordingComplete: setRecording,
    onError: (_msg, code) => setErrorCode(code ?? 'failed'),
  });
  const { isRecording, recordingDuration, startRecording, stopRecording, cancelRecording } = recorder;

  const previewUrl = useMemo(() => (recording ? URL.createObjectURL(recording.blob) : null), [recording]);
  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const start = useCallback(() => {
    setErrorCode(null);
    setRecording(null);
    startRecording();
  }, [startRecording]);

  const cancel = useCallback(() => {
    if (isRecording) cancelRecording();
    onCancel();
  }, [isRecording, cancelRecording, onCancel]);

  const save = useCallback(async () => {
    if (!recording) return;
    setSaving(true);
    setErrorCode(null);
    const ok = await onSave(recording);
    setSaving(false);
    if (!ok) setErrorCode('save');
  }, [recording, onSave]);

  const errorText = errorCode === 'denied' ? labels.micDenied
    : errorCode === 'save' ? labels.saveFailed
      : errorCode ? labels.micUnavailable : null;

  return (
    <Box data-testid="voice-note-recorder" sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1.5, px: 1, pb: 1 }}>
      {!recording && (
        <>
          <ButtonBase
            onClick={isRecording ? stopRecording : start}
            aria-label={isRecording ? labels.stop : labels.record}
            sx={{
              width: 64,
              height: 64,
              borderRadius: '50%',
              bgcolor: isRecording ? 'error.main' : 'primary.main',
              color: '#fff',
              transition: 'background-color 0.15s',
              '&.Mui-focusVisible': { outline: '3px solid', outlineColor: 'primary.light', outlineOffset: 2 },
            }}
          >
            {isRecording ? <Stop sx={{ fontSize: 30 }} /> : <Mic sx={{ fontSize: 30 }} />}
          </ButtonBase>
          <Typography
            role="timer"
            aria-live="off"
            sx={{ fontFamily: 'monospace', fontSize: 15, fontWeight: 600, color: isRecording ? 'error.main' : 'text.secondary' }}
          >
            {formatDuration(recordingDuration)} / {formatDuration(VOICE_NOTE_MAX_SEC)}
          </Typography>
          {!isRecording && !errorText && (
            <Typography sx={{ fontSize: 13, color: 'text.secondary', textAlign: 'center' }}>{labels.hint}</Typography>
          )}
        </>
      )}

      {recording && previewUrl && (
        <audio data-testid="voice-note-preview" src={previewUrl} controls style={{ width: '100%', maxWidth: 360 }} />
      )}

      {errorText && (
        <Typography role="alert" sx={{ fontSize: 13, color: 'error.main', textAlign: 'center' }}>
          {errorText}
        </Typography>
      )}

      <Box sx={{ display: 'flex', gap: 1, justifyContent: 'flex-end', alignSelf: 'stretch', flexWrap: 'wrap' }}>
        <Button onClick={cancel} disabled={saving} sx={{ minHeight: 44, textTransform: 'none', color: 'text.secondary' }}>
          {labels.cancel}
        </Button>
        {recording && (
          <>
            <Button onClick={start} disabled={saving} sx={{ minHeight: 44, textTransform: 'none', whiteSpace: 'nowrap' }}>
              {labels.rerecord}
            </Button>
            <Button
              variant="contained"
              onClick={save}
              disabled={saving}
              startIcon={saving ? <CircularProgress size={14} color="inherit" /> : undefined}
              sx={{ minHeight: 44, px: 3, textTransform: 'none', whiteSpace: 'nowrap' }}
            >
              {saving ? labels.saving : labels.save}
            </Button>
          </>
        )}
      </Box>
    </Box>
  );
}
