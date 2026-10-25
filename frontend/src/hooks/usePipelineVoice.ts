/**
 * usePipelineVoice — the voice pipeline prototype (2026-10-25): the student's speech is transcribed
 * by Google's transcription-only Live model, the words go to the TEXT coach as an ordinary chat turn
 * (the page's sendMessage: every server mechanism, the board moved by the server, wrong sentences
 * withheld before they are shown), and the streamed answer is read aloud sentence by sentence by
 * Google's TTS (/api/coach/voice/tts). A canned filler («Сейчас посмотрю») plays at once so the
 * student hears something within a second while the coach thinks.
 *
 * Same shape as useGeminiLive for the composer (status, isActive, prepare, connect, disconnect), so
 * CoachChat switches between the two by `?voice=pipeline` (readVoiceMode).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { GoogleGenAI } from '@google/genai';
import type { LiveStatus } from './useGeminiLive';
import {
  FIRST_CHUNK_MAX_CHARS, INTERIM_REPLACE_MS, STT_RECONNECT_DELAYS_MS, STT_ROTATE_RETRY_MS, TTS_BLOCK_MS, TTS_IN_FLIGHT, extendsSentText, fillerFor,
  groupChunks, localeOf, looksLikeMove, movePhrase, newWords, rotationDue, speakable, splitLong, takeSentences, ttsRetryDelay, utteranceReady,
  type PipelineLocale,
} from '@/lib/coach/voice-pipeline';
import { gameFromActions } from '@/lib/coach/voice-game';

export type VoiceMode = 'live' | 'pipeline';

/** `?voice=pipeline` in the address, else localStorage `coachVoiceMode`, else the build's default. */
export function readVoiceMode(): VoiceMode {
  if (typeof window === 'undefined') return 'live';
  try {
    const q = new URLSearchParams(window.location.search).get('voice');
    if (q === 'pipeline' || q === 'live') {
      try { window.localStorage.setItem('coachVoiceMode', q); } catch { /* storage may be blocked */ }
      return q;
    }
    const stored = window.localStorage.getItem('coachVoiceMode');
    if (stored === 'pipeline' || stored === 'live') return stored;
  } catch {
    /* storage may be blocked */
  }
  return process.env.NEXT_PUBLIC_COACH_VOICE_MODE === 'pipeline' ? 'pipeline' : 'live';
}

export interface PipelineFrame {
  delta?: string;
  stage?: string;
  done?: boolean;
  /** The server's board actions of this frame: a `game` view with the move just played is read out at once. */
  board_actions?: unknown;
}

export interface UsePipelineVoiceOptions {
  /** The student's utterance, final: the page sends it to the text coach. */
  onUtterance: (text: string) => void;
  /** The interface language, the fallback when the words do not tell. */
  locale?: () => string;
  onError?: (msg: string) => void;
}

export interface PipelineTimings {
  /** End of the student's speech → the words sent to the coach. */
  sttMs: number | null;
  /** End of the student's speech → the first sound (the filler). */
  firstSoundMs: number | null;
  /** End of the student's speech → the first spoken sentence of the answer itself. */
  firstAnswerMs: number | null;
}

const OUTPUT_SAMPLE_RATE = 24000;
const SPEECH_RMS = 0.02;
const BARGE_IN_RMS = 0.05;
const BARGE_IN_SUSTAIN_MS = 250;
const TICK_MS = 100;

/** One chunk of the answer on its way to the speaker: fetched ahead (TTS_IN_FLIGHT at a time), played in order. */
interface Piece {
  text: string;
  locale: PipelineLocale;
  parts: Int16Array[];
  played: number;     // parts already handed to playback
  started: boolean;
  done: boolean;
}

interface Turn {
  id: number;
  controller: AbortController;
  buffer: string;
  waiting: string[];  // short sentences held for the next one (groupChunks)
  quiet: boolean;      // the quick reaction streams: not read aloud (the filler stands for it)
  pieces: Piece[];     // the chunks queued for reading, in order; a piece leaves once it is played out
  firstQueued: boolean;  // the first chunk went alone and short, for the earliest first word
  factSpoken: boolean;   // the move of the game was read out from the server's view (movePhrase)
  spokenAnswer: boolean;
  done: boolean;
}

interface LiveSessionLike {
  sendRealtimeInput: (input: { audio: { data: string; mimeType: string } }) => void;
  close: () => void;
}

function toBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

export default function usePipelineVoice(options: UsePipelineVoiceOptions) {
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const [status, setStatusState] = useState<LiveStatus>('idle');
  const statusRef = useRef<LiveStatus>('idle');
  const setStatus = useCallback((s: LiveStatus) => { statusRef.current = s; setStatusState(s); }, []);
  const [isActive, setIsActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [timings, setTimings] = useState<PipelineTimings>({ sttMs: null, firstSoundMs: null, firstAnswerMs: null });
  // Whether the reading works: «quota» once a chunk was left unread for a 429 that no waiting cured, «down»
  // for a failing TTS — the page tells the student to read the text; back to «ok» on the next chunk read.
  const [ttsState, setTtsState] = useState<'ok' | 'quota' | 'down'>('ok');
  const ttsBlockedUntilRef = useRef(0);

  const streamRef = useRef<MediaStream | null>(null);
  const captureCtxRef = useRef<AudioContext | null>(null);
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const sessionRef = useRef<LiveSessionLike | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // The transcription connection lives about ten minutes: when this one was opened, whether the server
  // said goAway, and whether a fresh one is being opened to take over (rotationDue, 25.10).
  const openedAtRef = useRef(0);
  const goAwayRef = useRef(false);
  const rotatingRef = useRef(false);
  const rotateRef = useRef<(reason: 'soft' | 'hard') => void>(() => {});

  // The transcript as the model keeps it, and what of it was already sent.
  const transcriptRef = useRef('');
  const baselineRef = useRef('');
  // The last utterance sent from an interim transcript, and when: the model's final may replace it whole.
  const interimSentRef = useRef<{ text: string; at: number } | null>(null);
  const lastChangeAtRef = useRef(0);
  const lastSpeechAtRef = useRef<number | null>(null);
  const speechEndAtRef = useRef<number | null>(null);
  const bargeLoudMsRef = useRef(0);

  const playSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());
  const nextPlayTimeRef = useRef(0);
  const turnRef = useRef<Turn | null>(null);
  const turnSeqRef = useRef(0);
  const fillerCacheRef = useRef<Map<string, Int16Array>>(new Map());

  const isSupported =
    typeof window !== 'undefined' &&
    typeof AudioWorkletNode !== 'undefined' &&
    !!(window.AudioContext || (window as unknown as { webkitAudioContext?: unknown }).webkitAudioContext) &&
    !!navigator?.mediaDevices?.getUserMedia;

  // ── playback ──────────────────────────────────────────────────────────────
  const stopSources = useCallback(() => {
    playSourcesRef.current.forEach((src) => {
      try { src.onended = null; src.stop(); } catch { /* already stopped */ }
    });
    playSourcesRef.current.clear();
    nextPlayTimeRef.current = 0;
  }, []);

  const enqueue = useCallback((int16: Int16Array, onFirst?: () => void) => {
    const ctx = playbackCtxRef.current;
    if (!ctx || int16.length === 0) return;
    const float = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) float[i] = int16[i] / 0x8000;
    const buffer = ctx.createBuffer(1, float.length, OUTPUT_SAMPLE_RATE);
    buffer.getChannelData(0).set(float);
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(ctx.destination);
    const startAt = Math.max(ctx.currentTime, nextPlayTimeRef.current);
    src.start(startAt);
    nextPlayTimeRef.current = startAt + buffer.duration;
    playSourcesRef.current.add(src);
    if (statusRef.current !== 'speaking') setStatus('speaking');
    onFirst?.();
    src.onended = () => {
      playSourcesRef.current.delete(src);
      const turn = turnRef.current;
      if (playSourcesRef.current.size === 0 && statusRef.current === 'speaking' && (!turn || (turn.done && turn.pieces.length === 0))) {
        setStatus('listening');
      }
    };
  }, [setStatus]);

  const endTurn = useCallback(() => {
    const turn = turnRef.current;
    if (turn) {
      turn.controller.abort();
      turn.done = true;
    }
    turnRef.current = null;
    stopSources();
    if (statusRef.current === 'speaking') setStatus('listening');
  }, [stopSources, setStatus]);

  // ── the answer, read aloud ────────────────────────────────────────────────
  // The pieces of a turn are fetched ahead, TTS_IN_FLIGHT at a time (OpenRouter answers a chunk whole, ~3 s
  // for a short one, 25.10), and played strictly in order: the head piece's parts go to the speaker as they
  // come, the next piece waits its turn with its audio already in hand.
  const drainRef = useRef<(turn: Turn) => void>(() => {});
  const startFetchesRef = useRef<(turn: Turn) => void>(() => {});

  const drain = useCallback((turn: Turn) => {
    if (turnRef.current !== turn || turn.controller.signal.aborted) return;
    while (turn.pieces.length) {
      const head = turn.pieces[0];
      for (; head.played < head.parts.length; head.played++) {
        enqueue(head.parts[head.played], () => {
          if (!turn.spokenAnswer) {
            turn.spokenAnswer = true;
            const end = speechEndAtRef.current;
            if (end !== null) setTimings((t) => ({ ...t, firstAnswerMs: Math.round(performance.now() - end) }));
          }
        });
      }
      if (!head.done) break;
      turn.pieces.shift();
    }
    if (turn.done && turn.pieces.length === 0 && playSourcesRef.current.size === 0 && statusRef.current === 'speaking') setStatus('listening');
  }, [enqueue, setStatus]);
  drainRef.current = drain;

  const fetchPiece = useCallback(async (turn: Turn, piece: Piece) => {
    piece.started = true;
    const text = speakable(piece.text);
    try {
      if (!text || turn.controller.signal.aborted) return;
      const call = () => fetch('/api/coach/voice/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ text, locale: piece.locale }),
        signal: turn.controller.signal,
      });
      const blocked = performance.now() < ttsBlockedUntilRef.current;
      let res = await call();
      let attempt = 0;
      let waited = 0;
      while (!res.ok) {
        // The minute's quota (429) is waited out and the chunk is read in its turn — no sentence is
        // dropped from the reading (25.10); a blip (5xx) gets a second, three times. Once a chunk was
        // left unread anyway, the next ones get one try each for a minute (TTS_BLOCK_MS).
        const delay = blocked ? null : ttsRetryDelay(res.status, attempt, waited);
        if (delay === null) {
          if (res.status === 429 || res.status === 402 || res.status >= 500) {
            ttsBlockedUntilRef.current = performance.now() + TTS_BLOCK_MS;
            setTtsState(res.status === 429 ? 'quota' : 'down');
          }
          return;  // the text stands alone on the screen
        }
        console.warn('[pipeline] tts', res.status, 'waiting', delay, 'ms');
        attempt += 1;
        waited += delay;
        await new Promise((r) => setTimeout(r, delay));
        if (turn.controller.signal.aborted) return;
        res = await call();
      }
      if (!res.body) return;
      if (ttsBlockedUntilRef.current) { ttsBlockedUntilRef.current = 0; setTtsState('ok'); }
      const reader = res.body.getReader();
      let carry: Uint8Array | null = null;
      for (;;) {
        const { value, done } = await reader.read();
        if (done || turn.controller.signal.aborted) break;
        let bytes = value;
        if (carry) { const merged = new Uint8Array(carry.length + bytes.length); merged.set(carry); merged.set(bytes, carry.length); bytes = merged; carry = null; }
        const even = bytes.length - (bytes.length % 2);
        if (even < bytes.length) carry = bytes.slice(even);
        if (even > 0) {
          piece.parts.push(new Int16Array(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + even)));
          drainRef.current(turn);
        }
      }
    } catch {
      /* aborted by a barge-in, or the TTS is down: the text is on the screen anyway */
    } finally {
      piece.done = true;
      drainRef.current(turn);
      startFetchesRef.current(turn);
    }
  }, []);

  const startFetches = useCallback((turn: Turn) => {
    if (turnRef.current !== turn || turn.controller.signal.aborted) return;
    let inFlight = turn.pieces.filter((p) => p.started && !p.done).length;
    for (const piece of turn.pieces) {
      if (inFlight >= TTS_IN_FLIGHT) break;
      if (!piece.started) { inFlight += 1; void fetchPiece(turn, piece); }
    }
  }, [fetchPiece]);
  startFetchesRef.current = startFetches;

  const feedFrame = useCallback((frame: PipelineFrame) => {
    const turn = turnRef.current;
    if (!turn || turn.controller.signal.aborted) return;
    if (frame.stage === 'quick') turn.quiet = true;
    else if (frame.stage === 'answer') turn.quiet = false;
    if (typeof frame.delta === 'string' && frame.delta && !turn.quiet) turn.buffer += frame.delta;
    const locale = localeOf(turn.buffer || turn.waiting.join(' '), (optionsRef.current.locale?.() as PipelineLocale) || 'ru');
    if (frame.board_actions && !turn.factSpoken) {
      // The server played the move and got the engine's reply before the model spoke: say so now.
      const view = gameFromActions(frame.board_actions);
      const phrase = view ? movePhrase(view, locale) : null;
      if (phrase) {
        turn.factSpoken = true;
        turn.pieces.push({ text: phrase, locale, parts: [], played: 0, started: false, done: false });
        turn.firstQueued = true;
        startFetches(turn);
      }
    }
    const { sentences, rest } = takeSentences(turn.buffer, !!frame.done);
    turn.buffer = rest;
    const all = [...turn.waiting, ...sentences];
    let chunks: string[];
    let waiting: string[];
    if (!turn.firstQueued && all.length) {
      // The first sentence goes alone and short: the first word of the answer as early as the TTS allows.
      const [head, ...tail] = all;
      const grouped = groupChunks(tail, !!frame.done);
      chunks = [...splitLong(head, FIRST_CHUNK_MAX_CHARS), ...grouped.chunks.flatMap((c) => splitLong(c))];
      waiting = grouped.waiting;
    } else {
      const grouped = groupChunks(all, !!frame.done);
      chunks = grouped.chunks.flatMap((c) => splitLong(c));
      waiting = grouped.waiting;
    }
    turn.waiting = waiting;
    for (const text of chunks) {
      turn.pieces.push({ text, locale, parts: [], played: 0, started: false, done: false });
      turn.firstQueued = true;
    }
    startFetches(turn);
    if (frame.done) {
      turn.done = true;
      drain(turn);
    }
  }, [startFetches, drain]);

  const playFiller = useCallback(async (turn: Turn, locale: PipelineLocale) => {
    const path = fillerFor(locale);
    try {
      let pcm = fillerCacheRef.current.get(path);
      if (!pcm) {
        const res = await fetch(path, { signal: turn.controller.signal });
        if (!res.ok) return;
        const buf = await res.arrayBuffer();
        pcm = new Int16Array(buf.slice(0, buf.byteLength - (buf.byteLength % 2)));
        fillerCacheRef.current.set(path, pcm);
      }
      if (turn.controller.signal.aborted) return;
      enqueue(pcm, () => {
        const end = speechEndAtRef.current;
        if (end !== null) setTimings((t) => ({ ...t, firstSoundMs: Math.round(performance.now() - end) }));
      });
    } catch {
      /* no filler: the answer's own sentences come soon */
    }
  }, [enqueue]);

  // ── the student's words ───────────────────────────────────────────────────
  const sendUtterance = useCallback((text: string) => {
    const previous = turnRef.current;
    if (previous) { previous.controller.abort(); previous.done = true; }
    stopSources();
    const turn: Turn = { id: ++turnSeqRef.current, controller: new AbortController(), buffer: '', waiting: [], quiet: false, pieces: [], firstQueued: false, factSpoken: false, spokenAnswer: false, done: false };
    turnRef.current = turn;
    const end = speechEndAtRef.current;
    setTimings({ sttMs: end !== null ? Math.round(performance.now() - end) : null, firstSoundMs: null, firstAnswerMs: null });
    const locale = localeOf(text, (optionsRef.current.locale?.() as PipelineLocale) || 'ru');
    // No «сейчас посмотрю» before a silence (the TTS is down) nor before a move: its own phrase comes within a second.
    if (performance.now() >= ttsBlockedUntilRef.current && !looksLikeMove(text)) void playFiller(turn, locale);
    try {
      optionsRef.current.onUtterance(text);
    } catch (err) {
      console.error('[pipeline] onUtterance failed', err);
    }
  }, [playFiller, stopSources]);

  const sendUtteranceRef = useRef(sendUtterance);
  sendUtteranceRef.current = sendUtterance;

  const tick = useCallback(() => {
    const now = performance.now();
    const transcript = transcriptRef.current;
    if (sessionRef.current && !rotatingRef.current) {
      const due = rotationDue(now, openedAtRef.current, lastSpeechAtRef.current, newWords(transcript, baselineRef.current) !== '', goAwayRef.current);
      if (due) rotateRef.current(due);
    }
    if (!utteranceReady(transcript, now, lastChangeAtRef.current, lastSpeechAtRef.current)) return;
    const words = newWords(transcript, baselineRef.current);
    baselineRef.current = transcript;
    if (!words) return;
    interimSentRef.current = { text: words, at: now };
    sendUtterance(words);
  }, [sendUtterance]);

  // ── media ─────────────────────────────────────────────────────────────────
  const acquireMedia = useCallback(async () => {
    const Ctor = (window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext) as typeof AudioContext | undefined;
    if (!Ctor) throw new Error('AudioContext is not available');
    if (!streamRef.current) {
      streamRef.current = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    }
    if (!captureCtxRef.current) captureCtxRef.current = new Ctor();
    if (!playbackCtxRef.current) playbackCtxRef.current = new Ctor({ sampleRate: OUTPUT_SAMPLE_RATE });
    for (const ctx of [captureCtxRef.current, playbackCtxRef.current]) {
      if (ctx.state !== 'running') { try { await ctx.resume(); } catch { /* fine */ } }
    }
  }, []);

  const cleanup = useCallback(() => {
    if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
    endTurn();
    try { workletNodeRef.current?.port && (workletNodeRef.current.port.onmessage = null); workletNodeRef.current?.disconnect(); } catch { /* fine */ }
    try { sourceNodeRef.current?.disconnect(); } catch { /* fine */ }
    workletNodeRef.current = null;
    sourceNodeRef.current = null;
    try { sessionRef.current?.close(); } catch { /* fine */ }
    sessionRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    for (const ref of [captureCtxRef, playbackCtxRef]) {
      try { void ref.current?.close(); } catch { /* fine */ }
      ref.current = null;
    }
    transcriptRef.current = '';
    baselineRef.current = '';
  }, [endTurn]);

  const fail = useCallback((msg: string) => {
    cleanup();
    setError(msg);
    setStatus('error');
    setIsActive(false);
    try { optionsRef.current.onError?.(msg); } catch { /* fine */ }
  }, [cleanup, setStatus]);

  const prepare = useCallback(async () => {
    try {
      await acquireMedia();
    } catch (err) {
      fail(err instanceof Error && /NotAllowed|Permission/i.test(err.message) ? 'Нет доступа к микрофону' : 'Микрофон недоступен');
      throw err;
    }
  }, [acquireMedia, fail]);

  // One transcription connection: a fresh token (each is for one connection), the Live model that only
  // transcribes, and the callbacks that act only while this connection is the current one.
  const openStt = useCallback(async (): Promise<LiveSessionLike> => {
    const res = await fetch('/api/coach/live-token', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
      body: JSON.stringify({ mode: 'stt', locale: optionsRef.current.locale?.() || 'ru' }),
    });
    if (!res.ok) throw new Error(`token ${res.status}`);
    const { token, model, transcription } = (await res.json()) as { token: string; model: string; transcription?: Record<string, unknown> };
    const ai = new GoogleGenAI({ apiKey: token, httpOptions: { apiVersion: 'v1alpha' } });
    const holder: { s: LiveSessionLike | null } = { s: null };
    const session = (await ai.live.connect({
        model,
        config: { inputAudioTranscription: transcription ?? {} } as never,
        callbacks: {
          onopen: () => { /* connected */ },
          onmessage: (m: unknown) => {
            if (holder.s && sessionRef.current !== holder.s) return;  // an old connection on its way out
            if ((m as { goAway?: unknown }).goAway) {
              goAwayRef.current = true;  // the server will close this connection soon: a fresh one takes over in a quiet moment
              console.info('[pipeline] stt goAway');
            }
            const sc = (m as { serverContent?: Record<string, unknown> }).serverContent;
            if (!sc) return;
            const interim = (sc.interimInputTranscription as { text?: string } | undefined)?.text;
            const final = (sc.inputTranscription as { text?: string } | undefined)?.text;
            const text = final ?? interim;
            if (typeof text === 'string' && text && text !== transcriptRef.current) {
              // A shorter text than the baseline: the model began a new transcript — start over.
              if (baselineRef.current && !text.startsWith(baselineRef.current.slice(0, 8))) baselineRef.current = '';
              transcriptRef.current = text;
              lastChangeAtRef.current = performance.now();
            }
            if (typeof final === 'string' && final.trim()) {
              // The model's final transcript: the utterance goes now (the interim fallback waits longer).
              const sent = interimSentRef.current;
              const whole = newWords(final, '');
              if (sent && performance.now() - sent.at < INTERIM_REPLACE_MS && extendsSentText(whole, sent.text)) {
                // The interim text went out a moment ago and this is the same utterance, whole: the partial
                // turn is replaced (the page aborts it), not followed by its tail as a second turn.
                interimSentRef.current = null;
                baselineRef.current = final;
                transcriptRef.current = final;
                sendUtteranceRef.current(whole);
              } else {
                const words = newWords(final, baselineRef.current);
                baselineRef.current = final;
                transcriptRef.current = final;
                interimSentRef.current = null;
                if (words) sendUtteranceRef.current(words);
              }
            }
            const activity = (sc.voiceActivity as { speechState?: string } | undefined)?.speechState;
            if (activity === 'SPEECH') {
              lastSpeechAtRef.current = performance.now();
              if (statusRef.current === 'speaking') endTurn();  // barge-in: the student talks over the coach
            }
          },
          onerror: (e: unknown) => console.warn('[pipeline] stt error', e),
          onclose: () => {
            if (!holder.s || sessionRef.current !== holder.s) return;  // closed on purpose (a swap, or the stop)
            sessionRef.current = null;
            if (statusRef.current !== 'idle' && tickRef.current) void reconnectRef.current();
          },
        },
      })) as unknown as LiveSessionLike;
    holder.s = session;
    openedAtRef.current = performance.now();
    goAwayRef.current = false;
    return session;
  }, [endTurn]);

  // A fresh connection takes over before this one's lifetime ends: opened first, swapped in, the old one
  // closed. «hard» (overdue, the student still talking): the words heard so far go to the coach first.
  const rotate = useCallback(async (reason: 'soft' | 'hard') => {
    if (rotatingRef.current || !sessionRef.current) return;
    rotatingRef.current = true;
    try {
      const fresh = await openStt();
      const old = sessionRef.current;
      if (!tickRef.current || !old) { try { fresh.close(); } catch { /* fine */ } return; }
      if (reason === 'hard') {
        const words = newWords(transcriptRef.current, baselineRef.current);
        if (words) sendUtteranceRef.current(words);
      }
      transcriptRef.current = '';
      baselineRef.current = '';
      sessionRef.current = fresh;
      try { old.close(); } catch { /* fine */ }
      console.info('[pipeline] stt connection rotated', reason);
    } catch (err) {
      console.warn('[pipeline] stt rotation failed, trying again later', err);
      openedAtRef.current += STT_ROTATE_RETRY_MS;
    } finally {
      rotatingRef.current = false;
    }
  }, [openStt]);
  rotateRef.current = rotate;

  // The connection dropped on its own: a new one, a few tries; what was heard before the drop goes to the
  // coach; only when every try fails does the microphone stop with a message.
  const reconnect = useCallback(async () => {
    if (statusRef.current === 'listening') setStatus('connecting');
    for (let i = 0; i < STT_RECONNECT_DELAYS_MS.length; i++) {
      await new Promise((r) => setTimeout(r, STT_RECONNECT_DELAYS_MS[i]));
      if (!tickRef.current) return;  // stopped meanwhile
      try {
        const fresh = await openStt();
        if (!tickRef.current) { try { fresh.close(); } catch { /* fine */ } return; }
        const words = newWords(transcriptRef.current, baselineRef.current);
        transcriptRef.current = '';
        baselineRef.current = '';
        sessionRef.current = fresh;
        if (statusRef.current === 'connecting') setStatus('listening');
        console.warn('[pipeline] stt reconnected after a drop, try', i + 1);
        if (words) sendUtteranceRef.current(words);
        return;
      } catch (err) {
        console.warn('[pipeline] stt reconnect failed, try', i + 1, err);
      }
    }
    fail('Соединение прервалось — нажмите микрофон ещё раз');
  }, [openStt, fail, setStatus]);
  const reconnectRef = useRef(reconnect);
  reconnectRef.current = reconnect;

  const connect = useCallback(async () => {
    if (sessionRef.current) return;
    setError(null);
    setStatus('connecting');
    try {
      await acquireMedia();
      sessionRef.current = await openStt();

      const ctx = captureCtxRef.current!;
      const stream = streamRef.current!;
      await ctx.audioWorklet.addModule('/worklets/pcm-capture-processor.js');
      const source = ctx.createMediaStreamSource(stream);
      const node = new AudioWorkletNode(ctx, 'pcm-capture-processor');
      sourceNodeRef.current = source;
      workletNodeRef.current = node;
      node.port.onmessage = (ev: MessageEvent) => {
        const data = ev.data as { pcm: ArrayBuffer; rms: number };
        if (!data?.pcm) return;
        const now = performance.now();
        if (data.rms > SPEECH_RMS) {
          lastSpeechAtRef.current = now;
          speechEndAtRef.current = now;
        }
        if (statusRef.current === 'speaking') {
          if (data.rms > BARGE_IN_RMS) {
            bargeLoudMsRef.current += (data.pcm.byteLength / 2 / 16000) * 1000;
            if (bargeLoudMsRef.current >= BARGE_IN_SUSTAIN_MS) { bargeLoudMsRef.current = 0; endTurn(); }
          } else {
            bargeLoudMsRef.current = 0;
          }
        }
        try {
          sessionRef.current?.sendRealtimeInput({ audio: { data: toBase64(data.pcm), mimeType: 'audio/pcm;rate=16000' } });
        } catch { /* closing */ }
      };
      source.connect(node);
      node.connect(ctx.destination);
      tickRef.current = setInterval(tick, TICK_MS);
      setIsActive(true);
      setStatus('listening');
    } catch (err) {
      console.error('[pipeline] connect failed', err);
      fail('Голосовой режим сейчас недоступен — продолжайте текстом.');
    }
  }, [acquireMedia, fail, setStatus, tick, endTurn, openStt]);

  const disconnect = useCallback(() => {
    cleanup();
    setIsActive(false);
    setStatus('idle');
  }, [cleanup, setStatus]);

  useEffect(() => () => cleanup(), [cleanup]);

  return { status, isSupported, isActive, error, timings, ttsState, prepare, connect, disconnect, feedFrame };
}
