/**
 * useMoveVoiceNotes — list / record / delete / play the voice notes of one saved
 * game. The owner gets the full set; a shared-database viewer passes the share
 * token and can only list and play. Audio is fetched through short-lived signed
 * URLs, one shared <audio> element at a time.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '@clerk/nextjs';
import { apiFetch } from '@/lib/api';
import { pathCovers } from '@/lib/voiceNotes';
import type { VoiceRecording } from '@/hooks/useVoiceRecorder';

export interface MoveVoiceNote {
  id: string;
  node_path: string;
  mime_type: string;
  duration_ms: number;
  created_at: string;
}

interface Options {
  /** Saved user game id; null disables the hook (master games, drafts). */
  gameId: string | null;
  /** Share token of the database, for read-only viewers. */
  shareToken?: string | null;
  onError?: (kind: 'load' | 'save' | 'delete' | 'play') => void;
}

const EXT: Record<string, string> = { 'audio/webm': 'webm', 'audio/mp4': 'm4a', 'audio/ogg': 'ogg', 'audio/mpeg': 'mp3' };

export function useMoveVoiceNotes({ gameId, shareToken, onError }: Options) {
  const { getToken } = useAuth();
  // Tagged with the game it was loaded for, so another game's notes never show.
  const [loaded, setLoaded] = useState<{ gameId: string | null; notes: MoveVoiceNote[] }>({ gameId: null, notes: [] });
  const notes = useMemo(() => (loaded.gameId === gameId ? loaded.notes : []), [loaded, gameId]);
  const setNotes = useCallback((update: (prev: MoveVoiceNote[]) => MoveVoiceNote[]) => {
    setLoaded(cur => ({ gameId: cur.gameId, notes: update(cur.notes) }));
  }, []);
  const [playingPath, setPlayingPath] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  // Bumped on every play/stop so a slow signed-URL fetch can't start stale audio.
  const playRequestRef = useRef(0);
  const onErrorRef = useRef(onError);
  useEffect(() => { onErrorRef.current = onError; });

  const base = `${process.env.NEXT_PUBLIC_API_URL || ''}/api/games/${encodeURIComponent(gameId ?? '')}/voice-notes`;
  const tokenQuery = shareToken ? `share_token=${encodeURIComponent(shareToken)}` : '';

  // Via a ref: a getToken identity change must not re-run the list fetch.
  const getTokenRef = useRef(getToken);
  useEffect(() => { getTokenRef.current = getToken; });
  const authHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const token = await getTokenRef.current();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, []);

  const stop = useCallback(() => {
    playRequestRef.current++;
    audioRef.current?.pause();
    audioRef.current = null;
    setPlayingPath(null);
  }, []);

  useEffect(() => {
    if (!gameId) return;
    let cancelled = false;
    (async () => {
      try {
        const list = await apiFetch<MoveVoiceNote[]>(`${base}${tokenQuery ? `?${tokenQuery}` : ''}`, {
          headers: await authHeaders(),
        });
        if (!cancelled) setLoaded({ gameId, notes: Array.isArray(list) ? list : [] });
      } catch {
        if (!cancelled) onErrorRef.current?.('load');
      }
    })();
    return () => {
      cancelled = true;
      stop();
    };
  }, [gameId, base, tokenQuery, authHeaders, stop]);

  const paths = useMemo(() => new Set(notes.map(n => n.node_path)), [notes]);

  /** Uploads a recording for a move, replacing any note already on it. */
  const save = useCallback(async (nodePath: string, recording: VoiceRecording): Promise<boolean> => {
    if (!gameId) return false;
    const mime = recording.blob.type.split(';')[0] || 'audio/webm';
    const form = new FormData();
    form.append('file', recording.blob, `voice-note.${EXT[mime] ?? 'webm'}`);
    form.append('node_path', nodePath);
    form.append('duration_ms', String(Math.max(1, Math.round(recording.durationMs))));
    try {
      const note = await apiFetch<MoveVoiceNote>(base, {
        method: 'POST', headers: await authHeaders(), body: form, retries: 0,
      });
      setNotes(prev => [...prev.filter(n => n.node_path !== nodePath), note]);
      return true;
    } catch {
      onErrorRef.current?.('save');
      return false;
    }
  }, [gameId, base, authHeaders, setNotes]);

  const remove = useCallback(async (nodePath: string): Promise<boolean> => {
    const note = notes.find(n => n.node_path === nodePath);
    if (!note) return false;
    if (playingPath === nodePath) stop();
    try {
      await apiFetch(`${base}/${encodeURIComponent(note.id)}`, { method: 'DELETE', headers: await authHeaders(), retries: 0 });
      setNotes(prev => prev.filter(n => n.id !== note.id));
      return true;
    } catch {
      onErrorRef.current?.('delete');
      return false;
    }
  }, [notes, playingPath, base, authHeaders, stop, setNotes]);

  /** Drops the notes of a deleted move and every move after it in its line. */
  const removeFrom = useCallback(async (nodePath: string) => {
    if (!notes.some(n => pathCovers(nodePath, n.node_path))) return;
    if (playingPath && pathCovers(nodePath, playingPath)) stop();
    try {
      await apiFetch(`${base}?node_path=${encodeURIComponent(nodePath)}`, {
        method: 'DELETE', headers: await authHeaders(), retries: 0,
      });
      setNotes(prev => prev.filter(n => !pathCovers(nodePath, n.node_path)));
    } catch {
      onErrorRef.current?.('delete');
    }
  }, [notes, playingPath, base, authHeaders, stop, setNotes]);

  const toggle = useCallback(async (nodePath: string) => {
    if (playingPath === nodePath) {
      stop();
      return;
    }
    const note = notes.find(n => n.node_path === nodePath);
    if (!note) return;
    stop();
    const request = playRequestRef.current;
    setPlayingPath(nodePath);
    try {
      const { url } = await apiFetch<{ url: string }>(
        `${base}/${encodeURIComponent(note.id)}/url${tokenQuery ? `?${tokenQuery}` : ''}`,
        { headers: await authHeaders() },
      );
      if (request !== playRequestRef.current) return;
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => {
        if (audioRef.current === audio) stop();
      };
      await audio.play();
    } catch {
      if (request !== playRequestRef.current) return;
      stop();
      onErrorRef.current?.('play');
    }
  }, [playingPath, notes, base, tokenQuery, authHeaders, stop]);

  return { notes, paths, playingPath, save, remove, removeFrom, toggle };
}
