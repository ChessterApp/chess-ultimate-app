import { useState, useRef, useCallback, useEffect } from 'react';
import { GoogleGenAI, Modality } from '@google/genai';
import type {
  LiveServerMessage,
  LiveServerToolCall,
  LiveServerToolCallCancellation,
  Session,
} from '@google/genai';

/**
 * useGeminiLive — browser-side Gemini Live voice client for the AI Chess Coach (Phase 2).
 *
 * Audio engine only: mints an ephemeral token via POST /api/coach/live-token, opens a Live
 * session through the SDK (ephemeral token passed as apiKey), streams 16 kHz PCM mic audio up
 * via an AudioWorklet, and plays back 24 kHz model audio gaplessly with barge-in support.
 * No UI — callers wire the returned state/handlers into their own components (Phase 3).
 */

export type LiveStatus = 'idle' | 'connecting' | 'listening' | 'speaking' | 'error';

export interface UseGeminiLiveOptions {
  getFen?: () => string;
  /** Current coach session id, so the minted token carries the shared conversation memory. */
  getSessionId?: () => string | null | undefined;
  onTranscript?: (t: { role: 'user' | 'model'; text: string; final: boolean }) => void;
  onError?: (msg: string) => void;
  onStatusChange?: (s: LiveStatus) => void;
  /** Fired after a voice tool call resolves, so the UI can apply board actions / game lists. */
  onToolResult?: (name: string, result: unknown) => void;
}

export interface UseGeminiLiveReturn {
  status: LiveStatus;
  isSupported: boolean;
  isActive: boolean;
  error: string | null;
  /** Acquire mic + audio contexts inside the tap handler, before any network work. */
  prepare: () => Promise<void>;
  connect: () => Promise<void>;
  disconnect: () => void;
  sendBoardUpdate: (fen: string) => void;
}

// Gemini Live audio formats (non-negotiable, per spec).
const OUTPUT_SAMPLE_RATE = 24000;
// RMS above which local mic activity counts as barge-in while the model is speaking.
const BARGE_IN_RMS = 0.05;
// RMS above which a mic frame counts as speech — used to approximate VAD end
// (the user's last spoken frame) as the start of the time-to-first-audio window.
const SPEECH_RMS = 0.02;
// Cap a single tool call so the model never waits indefinitely on a slow tool;
// on timeout we reply with an error so it can verbally report it couldn't check.
const TOOL_CALL_TIMEOUT_MS = 10000;
// After this long on a healthy connection, restore the one-shot reconnect budget
// so a later, unrelated drop can still auto-recover.
const HEALTHY_RECONNECT_RESET_MS = 60000;

// Latency telemetry contract shared with Hermes POST /api/coach/metrics.
// 'end' is the session-lifecycle beacon fired on disconnect (carries session_ms);
// the server meters a voice session row from it.
type LiveMetricEvent = 'connect' | 'turn' | 'tool' | 'error' | 'end';
interface LiveMetricRecord {
  sessionId?: string;
  turn: number;
  event: LiveMetricEvent;
  ttfa_ms?: number;
  connect_ms?: number;
  token_ms?: number;
  tool_name?: string;
  tool_ms?: number;
  prompt_bytes?: number;
  /** Whole-session duration in ms, sent on the 'end' beacon. */
  session_ms?: number;
  /** Actual failure detail (DOMException name+message, or String(err)) for 'error' events. */
  error?: string;
  ts: number;
}

// Human/telemetry-readable failure text. Preserves the DOMException name (e.g.
// NotAllowedError) so a blocked mic is distinguishable from a network failure,
// both in the visible status pill and in the error metric.
function describeError(err: unknown, fallback: string): string {
  if (err instanceof DOMException) {
    return err.message ? `${err.name}: ${err.message}` : err.name;
  }
  if (err instanceof Error) {
    return err.message || fallback;
  }
  const s = String(err);
  return s && s !== '[object Object]' ? s : fallback;
}

function getAudioContextCtor(): typeof AudioContext | null {
  if (typeof window === 'undefined') return null;
  return (window.AudioContext ||
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext ||
    null) as typeof AudioContext | null;
}

function arrayBufferToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(
      null,
      Array.from(bytes.subarray(i, i + chunk)),
    );
  }
  return btoa(binary);
}

// Minimal per-move context line the live model reads as the new source of truth.
// Kept terse (just the FEN) so injected board updates don't bloat the turn.
function boardUpdateText(fen: string): string {
  return `Current position (FEN): ${fen}`;
}

function base64ToInt16(b64: string): Int16Array {
  const binary = atob(b64);
  const len = binary.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Int16Array(bytes.buffer, 0, Math.floor(len / 2));
}

export default function useGeminiLive(
  options: UseGeminiLiveOptions = {},
): UseGeminiLiveReturn {
  const [status, setStatusState] = useState<LiveStatus>('idle');
  const [isSupported, setIsSupported] = useState(false);
  const [isActive, setIsActive] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Keep the latest options accessible from stable callbacks without re-binding them.
  const optionsRef = useRef<UseGeminiLiveOptions>(options);
  optionsRef.current = options;

  const statusRef = useRef<LiveStatus>('idle');
  const sessionRef = useRef<Session | null>(null);
  // Latest resumable session handle from the server, used to reconnect after an
  // unexpected drop. Null until the server sends a resumable update.
  const resumptionHandleRef = useRef<string | null>(null);
  // Set when the user deliberately stops — suppresses auto-reconnect.
  const userStoppedRef = useRef(false);
  // Guards to a single automatic reconnect per user-initiated session.
  const reconnectUsedRef = useRef(false);
  // Timer that restores the reconnect budget after a stretch of healthy uptime.
  const healthyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Bumped whenever a connection is torn down or replaced, so close/error
  // callbacks from a stale session are ignored (they must not trigger a drop).
  const connGenRef = useRef(0);
  const streamRef = useRef<MediaStream | null>(null);
  const captureCtxRef = useRef<AudioContext | null>(null);
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  // The capture context the pcm-capture worklet module is currently loaded on.
  // Re-adding the module to the same context throws ("already registered"), so
  // on a reconnect that reuses the context we skip addModule.
  const workletLoadedCtxRef = useRef<AudioContext | null>(null);
  const playSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());
  const nextPlayTimeRef = useRef(0);
  // In-flight tool-call fetches, keyed by functionCall id, so a
  // toolCallCancellation can abort them.
  const toolAbortRef = useRef<Map<string, AbortController>>(new Map());

  // ── Latency instrumentation ────────────────────────────────────────────────
  // Turn counter for per-turn TTFA records.
  const turnRef = useRef(0);
  // performance.now() of the user's most recent spoken (above-threshold) mic
  // frame — approximates VAD end, the start of the time-to-first-audio window.
  const lastUserSpeechAtRef = useRef<number | null>(null);
  // True while we're still waiting for the first model audio chunk of a turn,
  // so TTFA is measured once per turn (reset when playback drains / on barge-in).
  const firstAudioPendingRef = useRef(true);

  const setStatus = useCallback((s: LiveStatus) => {
    statusRef.current = s;
    setStatusState(s);
    optionsRef.current.onStatusChange?.(s);
  }, []);

  // Fire-and-forget a latency record to Hermes via the metrics proxy. This runs
  // OFF the audio hot path: never awaited, fully wrapped in try/catch, so a slow
  // or failing metrics endpoint can never delay or break voice.
  // Wall-clock start of the current live session (set on connect), used to
  // compute session_ms for the 'end' metering beacon.
  const sessionStartRef = useRef<number | null>(null);

  const reportMetric = useCallback(
    (partial: Partial<LiveMetricRecord> & { event: LiveMetricEvent }) => {
      const record: LiveMetricRecord = {
        sessionId: optionsRef.current.getSessionId?.() ?? undefined,
        turn: partial.turn ?? turnRef.current,
        event: partial.event,
        ttfa_ms: partial.ttfa_ms,
        connect_ms: partial.connect_ms,
        token_ms: partial.token_ms,
        tool_name: partial.tool_name,
        tool_ms: partial.tool_ms,
        prompt_bytes: partial.prompt_bytes,
        session_ms: partial.session_ms,
        error: partial.error,
        ts: Date.now(),
      };
      try {
        console.debug('[live-metrics]', record);
        void fetch('/api/coach/metrics', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify(record),
          keepalive: true,
        }).catch(() => {
          /* telemetry only — swallow */
        });
      } catch {
        /* telemetry must never break the audio path */
      }
    },
    [],
  );

  // Detect capability once mounted (SSR-safe).
  useEffect(() => {
    const supported =
      typeof window !== 'undefined' &&
      getAudioContextCtor() !== null &&
      typeof AudioWorkletNode !== 'undefined' &&
      !!navigator?.mediaDevices?.getUserMedia;
    setIsSupported(supported);
  }, []);

  // Stop and clear all scheduled playback buffers.
  const stopSources = useCallback(() => {
    playSourcesRef.current.forEach((src) => {
      try {
        src.onended = null;
        src.stop();
      } catch {
        /* already stopped */
      }
    });
    playSourcesRef.current.clear();
    nextPlayTimeRef.current = 0;
  }, []);

  // Barge-in: flush playback and hand the floor back to the user.
  const flushPlayback = useCallback(() => {
    stopSources();
    // The interrupted turn is over — arm TTFA measurement for the next one.
    firstAudioPendingRef.current = true;
    if (statusRef.current === 'speaking') {
      setStatus('listening');
    }
  }, [stopSources, setStatus]);

  // Tear down the live session and audio graph. With { keepMedia: true } the
  // mic stream and both AudioContexts are left alive (and the worklet module
  // stays loaded) so a reconnect can reuse them without a fresh user gesture —
  // re-acquiring them off-gesture would fail on mobile Safari.
  const cleanup = useCallback((opts?: { keepMedia?: boolean }) => {
    const keepMedia = opts?.keepMedia ?? false;
    // Invalidate the active connection so its late close/error callbacks no-op.
    connGenRef.current += 1;
    if (healthyTimerRef.current) {
      clearTimeout(healthyTimerRef.current);
      healthyTimerRef.current = null;
    }
    toolAbortRef.current.forEach((controller) => {
      try {
        controller.abort();
      } catch {
        /* noop */
      }
    });
    toolAbortRef.current.clear();
    const node = workletNodeRef.current;
    if (node) {
      try {
        node.port.onmessage = null;
      } catch {
        /* noop */
      }
      try {
        node.disconnect();
      } catch {
        /* noop */
      }
      workletNodeRef.current = null;
    }
    if (sourceNodeRef.current) {
      try {
        sourceNodeRef.current.disconnect();
      } catch {
        /* noop */
      }
      sourceNodeRef.current = null;
    }
    if (!keepMedia && streamRef.current) {
      streamRef.current.getTracks().forEach((t) => {
        try {
          t.stop();
        } catch {
          /* noop */
        }
      });
      streamRef.current = null;
    }
    if (sessionRef.current) {
      try {
        sessionRef.current.close();
      } catch {
        /* noop */
      }
      sessionRef.current = null;
    }
    stopSources();
    if (!keepMedia) {
      if (captureCtxRef.current) {
        try {
          captureCtxRef.current.close();
        } catch {
          /* noop */
        }
        captureCtxRef.current = null;
      }
      if (playbackCtxRef.current) {
        try {
          playbackCtxRef.current.close();
        } catch {
          /* noop */
        }
        playbackCtxRef.current = null;
      }
      workletLoadedCtxRef.current = null;
    }
  }, [stopSources]);

  // Decode a base64 24 kHz PCM chunk and schedule it gaplessly.
  const enqueuePlayback = useCallback(
    (b64: string) => {
      const AudioCtor = getAudioContextCtor();
      if (!AudioCtor) return;
      if (!playbackCtxRef.current) {
        playbackCtxRef.current = new AudioCtor({ sampleRate: OUTPUT_SAMPLE_RATE });
      }
      const ctx = playbackCtxRef.current;

      const int16 = base64ToInt16(b64);
      if (int16.length === 0) return;

      // First audio chunk of a turn: record time-to-first-audio (VAD end →
      // first model audio). Measured once per turn, before any decode work.
      if (firstAudioPendingRef.current) {
        firstAudioPendingRef.current = false;
        const startedAt = lastUserSpeechAtRef.current;
        if (startedAt !== null) {
          turnRef.current += 1;
          reportMetric({
            event: 'turn',
            turn: turnRef.current,
            ttfa_ms: Math.round(performance.now() - startedAt),
          });
        }
      }

      const float = new Float32Array(int16.length);
      for (let i = 0; i < int16.length; i++) {
        float[i] = int16[i] / 0x8000;
      }

      const buffer = ctx.createBuffer(1, float.length, OUTPUT_SAMPLE_RATE);
      buffer.getChannelData(0).set(float);

      const src = ctx.createBufferSource();
      src.buffer = buffer;
      src.connect(ctx.destination);

      const startAt = Math.max(ctx.currentTime, nextPlayTimeRef.current);
      src.start(startAt);
      nextPlayTimeRef.current = startAt + buffer.duration;

      playSourcesRef.current.add(src);
      setStatus('speaking');

      src.onended = () => {
        playSourcesRef.current.delete(src);
        if (playSourcesRef.current.size === 0 && statusRef.current === 'speaking') {
          // Model finished this turn — arm TTFA measurement for the next one.
          firstAudioPendingRef.current = true;
          setStatus('listening');
        }
      };
    },
    [setStatus, reportMetric],
  );

  // Cancel in-flight tool fetches the model no longer wants a response for.
  const handleToolCancellation = useCallback(
    (cancellation: LiveServerToolCallCancellation) => {
      for (const id of cancellation.ids ?? []) {
        const controller = toolAbortRef.current.get(id);
        if (controller) {
          try {
            controller.abort();
          } catch {
            /* noop */
          }
          toolAbortRef.current.delete(id);
        }
      }
    },
    [],
  );

  // Run each functionCall through the /api/coach/tool proxy and reply with a
  // functionResponse for every call — even on failure — so the session never
  // stalls waiting on a tool.
  const handleToolCall = useCallback(async (toolCall: LiveServerToolCall) => {
    const calls = toolCall.functionCalls ?? [];
    const session = sessionRef.current;
    if (calls.length === 0 || !session) return;

    const sessionId = optionsRef.current.getSessionId?.() ?? undefined;

    const responses = await Promise.all(
      calls.map(async (fc) => {
        const controller = new AbortController();
        if (fc.id) toolAbortRef.current.set(fc.id, controller);
        const toolStart = performance.now();
        let aborted = false;
        // Bound the tool at 10s. A timeout aborts the same controller, so we flag
        // it to tell a slow-tool timeout apart from a model-initiated cancel.
        let timedOut = false;
        const timeout = setTimeout(() => {
          timedOut = true;
          try {
            controller.abort();
          } catch {
            /* noop */
          }
        }, TOOL_CALL_TIMEOUT_MS);
        try {
          const res = await fetch('/api/coach/tool', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
              name: fc.name,
              args: fc.args ?? {},
              session_id: sessionId,
            }),
            signal: controller.signal,
          });
          const data = await res.json().catch(() => ({}));
          if (!res.ok) {
            return {
              id: fc.id,
              name: fc.name,
              response: {
                error:
                  (data && (data as { error?: string }).error) ||
                  `Tool proxy error ${res.status}`,
              },
            };
          }
          try {
            optionsRef.current.onToolResult?.(fc.name ?? '', data);
          } catch {
            /* UI callback errors must not break the session */
          }
          return {
            id: fc.id,
            name: fc.name,
            response: { result: (data as { result?: unknown }).result ?? data },
          };
        } catch (err) {
          if (err instanceof DOMException && err.name === 'AbortError') {
            // Timed out — still answer, with an error, so the model can say out
            // loud it couldn't check instead of stalling the turn silently.
            if (timedOut) {
              return {
                id: fc.id,
                name: fc.name,
                response: {
                  error: `Tool "${fc.name ?? 'unknown'}" timed out after ${
                    TOOL_CALL_TIMEOUT_MS / 1000
                  }s`,
                },
              };
            }
            // Cancelled by the model — drop it, no response expected.
            aborted = true;
            return null;
          }
          const message = err instanceof Error ? err.message : 'tool call failed';
          return { id: fc.id, name: fc.name, response: { error: message } };
        } finally {
          clearTimeout(timeout);
          if (fc.id) toolAbortRef.current.delete(fc.id);
          // Per-call tool latency: functionCall received → response ready.
          // Skip cancelled calls (no response is sent for them).
          if (!aborted) {
            reportMetric({
              event: 'tool',
              tool_name: fc.name ?? undefined,
              tool_ms: Math.round(performance.now() - toolStart),
            });
          }
        }
      }),
    );

    const functionResponses = responses.filter(
      (r): r is NonNullable<typeof r> => r !== null,
    );
    if (functionResponses.length === 0) return;
    try {
      session.sendToolResponse({ functionResponses });
    } catch {
      /* session may be closing */
    }
  }, [reportMetric]);

  const handleMessage = useCallback(
    (msg: LiveServerMessage) => {
      // Keep the latest resumable handle so we can reconnect after a drop.
      const resume = msg.sessionResumptionUpdate;
      if (resume?.resumable && resume.newHandle) {
        resumptionHandleRef.current = resume.newHandle;
      }

      if (msg.toolCall) {
        void handleToolCall(msg.toolCall);
      }
      if (msg.toolCallCancellation) {
        handleToolCancellation(msg.toolCallCancellation);
      }

      const sc = msg.serverContent;
      if (!sc) return;

      if (sc.inputTranscription?.text) {
        optionsRef.current.onTranscript?.({
          role: 'user',
          text: sc.inputTranscription.text,
          final: !!sc.inputTranscription.finished,
        });
      }
      if (sc.outputTranscription?.text) {
        optionsRef.current.onTranscript?.({
          role: 'model',
          text: sc.outputTranscription.text,
          final: !!sc.outputTranscription.finished,
        });
      }

      if (sc.interrupted) {
        flushPlayback();
      }

      const parts = sc.modelTurn?.parts;
      if (parts) {
        for (const part of parts) {
          const inline = part.inlineData;
          if (inline?.data && inline.mimeType?.includes('audio/pcm')) {
            enqueuePlayback(inline.data);
          }
        }
      }
    },
    [flushPlayback, enqueuePlayback, handleToolCall, handleToolCancellation],
  );

  const fail = useCallback(
    (msg: string) => {
      cleanup();
      setIsActive(false);
      setError(msg);
      optionsRef.current.onError?.(msg);
      setStatus('error');
      // Carry the real failure detail into telemetry so the 'error' event is
      // diagnosable (previously it reported an empty error).
      reportMetric({ event: 'error', error: msg });
    },
    [cleanup, setStatus, reportMetric],
  );

  // Acquire the mic and BOTH AudioContexts. This is the gesture-critical step:
  // on mobile Safari the user-activation window closes after any network await,
  // so getUserMedia + AudioContext.resume() must run before token mint / WS
  // connect or they reject/stay suspended. Idempotent — on a reconnect it
  // reuses the still-alive stream and contexts and just re-resumes them.
  const acquireMedia = useCallback(async () => {
    const AudioCtor = getAudioContextCtor();
    if (!AudioCtor) throw new Error('AudioContext is not available');

    // Mic first, before any await that isn't the getUserMedia prompt itself.
    if (!streamRef.current) {
      streamRef.current = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    }

    // Capture context (native rate for mic input).
    if (!captureCtxRef.current) {
      captureCtxRef.current = new AudioCtor();
    }
    // Playback context (fixed 24 kHz model output). Created inside the gesture
    // too, so it isn't stuck suspended when the first model audio arrives.
    if (!playbackCtxRef.current) {
      playbackCtxRef.current = new AudioCtor({ sampleRate: OUTPUT_SAMPLE_RATE });
    }

    for (const ctx of [captureCtxRef.current, playbackCtxRef.current]) {
      if (ctx.state !== 'running' && typeof ctx.resume === 'function') {
        try {
          await ctx.resume();
        } catch {
          /* already running or closing — safe to ignore */
        }
      }
    }
  }, []);

  // Wire the held mic stream into the capture worklet and start streaming PCM.
  // Assumes acquireMedia() already ran, so the stream and capture context are
  // live — this only builds the audio graph (no getUserMedia, no ctx creation).
  const wireCapture = useCallback(
    async (session: Session) => {
      const ctx = captureCtxRef.current;
      const stream = streamRef.current;
      if (!ctx || !stream) throw new Error('Audio capture was not initialized');

      // Load the worklet module once per context; on a reused (reconnect)
      // context it is already registered, so re-adding it would throw.
      if (workletLoadedCtxRef.current !== ctx) {
        await ctx.audioWorklet.addModule('/worklets/pcm-capture-processor.js');
        workletLoadedCtxRef.current = ctx;
      }

      const source = ctx.createMediaStreamSource(stream);
      const node = new AudioWorkletNode(ctx, 'pcm-capture-processor');
      sourceNodeRef.current = source;
      workletNodeRef.current = node;

      node.port.onmessage = (ev: MessageEvent) => {
        const data = ev.data as { pcm: ArrayBuffer; rms: number };
        if (!data?.pcm) return;

        // Track the user's last spoken frame as the TTFA window start (VAD end
        // approximation). The mic streams continuously, so gate on speech energy.
        if (data.rms > SPEECH_RMS) {
          lastUserSpeechAtRef.current = performance.now();
        }

        // Local barge-in: user speaks over the coach.
        if (data.rms > BARGE_IN_RMS && statusRef.current === 'speaking') {
          flushPlayback();
        }

        try {
          session.sendRealtimeInput({
            audio: {
              data: arrayBufferToBase64(data.pcm),
              mimeType: 'audio/pcm;rate=16000',
            },
          });
        } catch {
          /* session may be closing */
        }
      };

      source.connect(node);
      node.connect(ctx.destination);
    },
    [flushPlayback],
  );

  // Lets the connection callbacks reach the drop handler without a dependency
  // cycle (the drop handler in turn re-opens the connection).
  const handleDropRef = useRef<(errMsg?: string) => void>(() => {});

  // Open a Live session. Pass a resumption handle to resume a dropped session
  // (fresh token, same conversation state) instead of starting a new one.
  const openConnection = useCallback(
    async (resumeHandle?: string) => {
      // Mic + AudioContexts first, BEFORE the token fetch and WS connect, so
      // the user-activation window is still open when getUserMedia runs.
      // Idempotent: on a reconnect this reuses the live stream/contexts.
      await acquireMedia();

      const fen = optionsRef.current.getFen?.();
      const sessionId = optionsRef.current.getSessionId?.();
      const tokenStart = performance.now();
      const res = await fetch('/api/coach/live-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          fen,
          session_id: sessionId ?? undefined,
          resume: resumeHandle ?? undefined,
        }),
      });
      if (!res.ok) {
        throw new Error(`Live coach unavailable (${res.status})`);
      }
      const { token, model, promptBytes } = (await res.json()) as {
        token?: string;
        model?: string;
        promptBytes?: number;
      };
      const tokenMs = Math.round(performance.now() - tokenStart);
      if (!token || !model) {
        throw new Error('Invalid live-token response');
      }

      const ai = new GoogleGenAI({
        apiKey: token,
        httpOptions: { apiVersion: 'v1alpha' },
      });

      const config: Record<string, unknown> = {
        responseModalities: [Modality.AUDIO],
        inputAudioTranscription: {},
        outputAudioTranscription: {},
      };
      if (resumeHandle) {
        config.sessionResumption = { handle: resumeHandle };
      }

      // Tag this connection; later teardown bumps the counter so a stale
      // session's close/error callback can't trigger a spurious reconnect.
      connGenRef.current += 1;
      const gen = connGenRef.current;

      const connectStart = performance.now();
      const session = await ai.live.connect({
        model,
        callbacks: {
          onmessage: handleMessage,
          onerror: (e: ErrorEvent) => {
            if (gen !== connGenRef.current) return;
            handleDropRef.current(e?.message || 'Live connection error');
          },
          onclose: () => {
            if (gen !== connGenRef.current) return;
            handleDropRef.current();
          },
        },
        config,
      });
      const connectMs = Math.round(performance.now() - connectStart);
      sessionRef.current = session;
      // Anchor session start for the 'end' duration beacon. Only set on the
      // first successful open so a mid-session reconnect keeps the original
      // start (session_ms reflects the whole conversation, not the last leg).
      if (sessionStartRef.current === null) {
        sessionStartRef.current = performance.now();
      }

      // Record connect-phase latency (token mint + WebSocket setup). Off the
      // hot path — a fresh turn's TTFA is measured separately.
      reportMetric({
        event: 'connect',
        token_ms: tokenMs,
        connect_ms: connectMs,
        prompt_bytes: typeof promptBytes === 'number' ? promptBytes : undefined,
      });

      // Anchor the initial position client-side so the coach is never blind to it,
      // regardless of whether the token's system instruction carried the FEN.
      if (fen) {
        try {
          session.sendClientContent({
            turns: [{ role: 'user', parts: [{ text: boardUpdateText(fen) }] }],
            turnComplete: false,
          });
        } catch {
          /* session may be closing */
        }
      }

      await wireCapture(session);

      setIsActive(true);
      setStatus('listening');

      // After a stretch of healthy uptime, restore the one-shot reconnect budget
      // so a later, unrelated drop can still auto-recover. Tied to this conn gen.
      if (healthyTimerRef.current) clearTimeout(healthyTimerRef.current);
      healthyTimerRef.current = setTimeout(() => {
        if (gen === connGenRef.current) {
          reconnectUsedRef.current = false;
        }
      }, HEALTHY_RECONNECT_RESET_MS);
    },
    [handleMessage, acquireMedia, wireCapture, setStatus, reportMetric],
  );

  // React to a session drop: reconnect ONCE with the stored handle if the drop
  // was unexpected; otherwise surface a terminal error state (deliberate stops
  // and already-surfaced errors are filtered out at the top).
  const handleDrop = useCallback(
    (errMsg?: string) => {
      if (userStoppedRef.current) return; // deliberate stop, handled by disconnect()
      if (statusRef.current === 'error') return; // already surfaced a failure

      const canReconnect =
        !reconnectUsedRef.current && !!resumptionHandleRef.current;
      if (canReconnect) {
        reconnectUsedRef.current = true;
        const handle = resumptionHandleRef.current as string;
        // Tear down the stale session + audio graph but KEEP the mic stream and
        // AudioContexts alive: reacquiring them off-gesture would fail on mobile
        // Safari. openConnection() re-resumes and re-wires them.
        cleanup({ keepMedia: true });
        setStatus('connecting');
        openConnection(handle).catch((err) => {
          fail(describeError(err, 'Failed to resume live coach'));
        });
        return;
      }

      // No handle (or reconnect already used): terminal. Deliberate stops and
      // already-surfaced errors returned at the top, so reaching here means an
      // unexpected drop we can't recover — surface it instead of going silently
      // idle, so the UI can prompt the user to restart.
      fail(errMsg ?? 'Live coach disconnected. Please restart to continue.');
    },
    [cleanup, fail, setStatus, openConnection],
  );
  handleDropRef.current = handleDrop;

  // Grab the mic + AudioContexts synchronously-first inside the user gesture,
  // before any network work (session create, token mint). Front-loading this is
  // what fixes mobile Safari: getUserMedia must run while user-activation is
  // still live. connect() re-acquires idempotently, so callers may skip this.
  const prepare = useCallback(async () => {
    if (sessionRef.current) return;
    setError(null);
    setStatus('connecting');
    try {
      await acquireMedia();
    } catch (err) {
      fail(describeError(err, 'Microphone access is required for voice mode'));
      throw err;
    }
  }, [acquireMedia, fail, setStatus]);

  const connect = useCallback(async () => {
    if (sessionRef.current) return;
    setError(null);
    setStatus('connecting');
    // Fresh user-initiated session: reset resumption/reconnect state.
    userStoppedRef.current = false;
    reconnectUsedRef.current = false;
    resumptionHandleRef.current = null;
    // Reset latency instrumentation for the new session.
    turnRef.current = 0;
    lastUserSpeechAtRef.current = null;
    firstAudioPendingRef.current = true;

    try {
      await openConnection();
    } catch (err) {
      // If the mic was granted but connect failed, fail() -> cleanup() stops the
      // held tracks so no mic indicator lingers.
      fail(describeError(err, 'Failed to start live coach'));
    }
  }, [setStatus, openConnection, fail]);

  const disconnect = useCallback(() => {
    userStoppedRef.current = true;
    // Session-end metering beacon: report the whole session's duration so the
    // server can record a voice session row. Only when a session actually opened.
    if (sessionStartRef.current !== null) {
      reportMetric({
        event: 'end',
        session_ms: Math.round(performance.now() - sessionStartRef.current),
      });
      sessionStartRef.current = null;
    }
    cleanup();
    setIsActive(false);
    setStatus('idle');
  }, [cleanup, setStatus, reportMetric]);

  // Push the current board position into the open session mid-conversation.
  // turnComplete:false injects context without interrupting the audio turn.
  const sendBoardUpdate = useCallback((fen: string) => {
    const session = sessionRef.current;
    if (!session || !fen) return;
    try {
      session.sendClientContent({
        turns: [{ role: 'user', parts: [{ text: boardUpdateText(fen) }] }],
        turnComplete: false,
      });
    } catch {
      /* session may be closing */
    }
  }, []);

  // Ensure resources are released on unmount.
  useEffect(() => {
    return () => {
      cleanup();
    };
  }, [cleanup]);

  return {
    status,
    isSupported,
    isActive,
    error,
    prepare,
    connect,
    disconnect,
    sendBoardUpdate,
  };
}
