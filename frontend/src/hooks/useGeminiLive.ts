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
  onTranscript?: (t: {
    role: 'user' | 'model';
    text: string;
    final: boolean;
    /** Turn correlation id for this utterance, so persisted rows join to events. */
    turnId?: string;
  }) => void;
  onError?: (msg: string) => void;
  onStatusChange?: (s: LiveStatus) => void;
  /** Fired after a voice tool call resolves, so the UI can apply board actions / game lists. */
  onToolResult?: (name: string, result: unknown) => void;
  /**
   * Fired when the monthly voice-minutes quota runs out — either the mint was
   * refused (429) or the local countdown reached zero and the session was ended.
   * The UI shows the "minutes used up" message instead of a connection error.
   */
  onQuotaExhausted?: () => void;
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
  /**
   * Voice minutes left this month, counted down locally from the mint response.
   * `null` when unknown (before connect), unlimited, or the quota lookup failed
   * open. Updated once per heartbeat tick while a session is live.
   */
  remainingSeconds: number | null;
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
// How often to report accumulated voice seconds to the metering ledger and to
// re-evaluate the local minutes countdown while a session is live.
const VOICE_HEARTBEAT_INTERVAL_MS = 60000;

// Latency + lifecycle telemetry contract shared with Hermes POST /api/coach/metrics.
// 'end' is the metering beacon fired on disconnect (carries session_ms; the server
// meters a voice session row from it); 'session_end' is the event-log lifecycle
// beacon (carries end_reason). Phase 2 also adds reconnect / tool_timeout /
// barge_in for full voice-path instrumentation in coach_events.
type LiveMetricEvent =
  | 'connect'
  | 'reconnect'
  | 'turn'
  | 'tool'
  | 'tool_timeout'
  | 'barge_in'
  | 'error'
  | 'drop'
  | 'end'
  | 'session_end';
/** Why a voice session ended, carried on the 'session_end' beacon. */
type SessionEndReason = 'user_stop' | 'quota_exhausted' | 'error' | 'drop';
interface LiveMetricRecord {
  sessionId?: string;
  turn: number;
  event: LiveMetricEvent;
  /** Per-utterance correlation id (client-generated UUID), on every beacon. */
  turn_id?: string;
  ttfa_ms?: number;
  connect_ms?: number;
  token_ms?: number;
  tool_name?: string;
  tool_ms?: number;
  prompt_bytes?: number;
  /** Whole-session duration in ms, sent on the 'end'/'session_end' beacons. */
  session_ms?: number;
  /** Actual failure detail (DOMException name+message, or String(err)) for 'error' events. */
  error?: string;
  /** Tool-call outcome + failure code on 'tool'/'tool_timeout' beacons. */
  ok?: boolean;
  error_code?: string;
  /** End reason on the 'session_end' beacon. */
  end_reason?: SessionEndReason;
  ts: number;
}

// Per-utterance correlation id. Prefers crypto.randomUUID (present in all voice-
// capable browsers + the test env); falls back to a random token so telemetry
// never throws where it's unavailable.
function genTurnId(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch {
    /* fall through */
  }
  return `t_${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`;
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
  // Voice minutes left this month (see UseGeminiLiveReturn.remainingSeconds).
  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(null);

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
  // Client-generated correlation id for the current utterance/turn. Set lazily
  // when a turn begins (user speech / a tool call) and cleared at turn end, so a
  // fresh turn gets a fresh id. Stamped on every beacon + the transcript rows.
  const turnIdRef = useRef<string | null>(null);
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

  // ── Voice minutes metering ─────────────────────────────────────────────────
  // Remaining seconds at connect time (from the mint response); null = unknown /
  // unlimited, so no local enforcement. The countdown is derived from this minus
  // session elapsed time.
  const quotaInitialRef = useRef<number | null>(null);
  // Seconds already reported to the metering ledger for this session, so each
  // heartbeat only sends the newly-elapsed delta (survives reconnects).
  const bookedSecondsRef = useRef(0);
  // Periodic heartbeat/countdown timer while a session is live.
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Set below (after disconnect is defined) to gracefully end a session when the
  // monthly quota is exhausted mid-call.
  const endForQuotaRef = useRef<() => void>(() => {});

  // Return the current turn's correlation id, minting one if a turn is in flight
  // without a user-speech frame yet (e.g. a model-initiated tool call).
  const ensureTurnId = useCallback((): string => {
    if (!turnIdRef.current) turnIdRef.current = genTurnId();
    return turnIdRef.current;
  }, []);

  const reportMetric = useCallback(
    (partial: Partial<LiveMetricRecord> & { event: LiveMetricEvent }) => {
      const record: LiveMetricRecord = {
        sessionId: optionsRef.current.getSessionId?.() ?? undefined,
        turn: partial.turn ?? turnRef.current,
        event: partial.event,
        turn_id: partial.turn_id ?? turnIdRef.current ?? undefined,
        ttfa_ms: partial.ttfa_ms,
        connect_ms: partial.connect_ms,
        token_ms: partial.token_ms,
        tool_name: partial.tool_name,
        tool_ms: partial.tool_ms,
        prompt_bytes: partial.prompt_bytes,
        session_ms: partial.session_ms,
        error: partial.error,
        ok: partial.ok,
        error_code: partial.error_code,
        end_reason: partial.end_reason,
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

  // Fire-and-forget a metering heartbeat to the voice-usage proxy (which sets
  // the user server-side and forwards to Hermes). Off the audio hot path: never
  // awaited, fully wrapped, keepalive so a final flush survives page unload.
  const postHeartbeat = useCallback((secondsDelta: number) => {
    if (secondsDelta <= 0) return;
    const sessionId = optionsRef.current.getSessionId?.() ?? undefined;
    if (!sessionId) return;
    try {
      void fetch('/api/coach/voice-usage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ session_id: sessionId, seconds_delta: secondsDelta }),
        keepalive: true,
      }).catch(() => {
        /* metering is best-effort — swallow */
      });
    } catch {
      /* metering must never break the audio path */
    }
  }, []);

  const stopHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
  }, []);

  // Book the seconds elapsed since the last heartbeat and, when metered, update
  // the local countdown — ending the session gracefully once it hits zero.
  const heartbeatTick = useCallback(() => {
    if (sessionStartRef.current === null) return;
    const elapsedSec = Math.floor(
      (performance.now() - sessionStartRef.current) / 1000,
    );
    const delta = elapsedSec - bookedSecondsRef.current;
    if (delta > 0) {
      postHeartbeat(delta);
      bookedSecondsRef.current = elapsedSec;
    }
    if (quotaInitialRef.current !== null) {
      const remaining = Math.max(0, quotaInitialRef.current - elapsedSec);
      setRemainingSeconds(remaining);
      if (remaining <= 0) {
        endForQuotaRef.current();
      }
    }
  }, [postHeartbeat]);

  // End-of-session telemetry: flush the residual metered seconds, then emit the
  // metering 'end' beacon (unchanged) and the 'session_end' lifecycle beacon
  // (with the end reason). Guarded on sessionStartRef so it fires exactly once
  // per session — it nulls sessionStartRef, so a later call is a no-op.
  const emitSessionEnd = useCallback(
    (reason: SessionEndReason) => {
      if (sessionStartRef.current === null) return;
      const elapsedMs = performance.now() - sessionStartRef.current;
      const residual = Math.floor(elapsedMs / 1000) - bookedSecondsRef.current;
      if (residual > 0) {
        postHeartbeat(residual);
        bookedSecondsRef.current += residual;
      }
      const session_ms = Math.round(elapsedMs);
      reportMetric({ event: 'end', session_ms });
      reportMetric({ event: 'session_end', session_ms, end_reason: reason });
      sessionStartRef.current = null;
    },
    [postHeartbeat, reportMetric],
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
    // The interrupted turn is over — arm TTFA measurement for the next one and
    // clear the turn id so the next utterance correlates under a fresh id.
    firstAudioPendingRef.current = true;
    turnIdRef.current = null;
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
    // Stop the metering/countdown timer; a reconnect restarts it in openConnection.
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
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
            turn_id: ensureTurnId(),
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
          // Model finished this turn — arm TTFA measurement for the next one and
          // clear the turn id so the next utterance gets a fresh one.
          firstAudioPendingRef.current = true;
          turnIdRef.current = null;
          setStatus('listening');
        }
      };
    },
    [setStatus, reportMetric, ensureTurnId],
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
        // Correlate this tool call with the current turn's events.
        const toolTurnId = ensureTurnId();
        const toolStart = performance.now();
        let aborted = false;
        // Bound the tool at 10s. A timeout aborts the same controller, so we flag
        // it to tell a slow-tool timeout apart from a model-initiated cancel.
        let timedOut = false;
        // Tool-call outcome, recorded on the 'tool' beacon (success/failure was
        // previously never captured). error_code distinguishes proxy vs network.
        let toolOk = true;
        let toolErrorCode: string | undefined;
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
            // Proxy/rate-limit rejection — the tool did NOT execute server-side,
            // so this outcome is captured only via the beacon.
            toolOk = false;
            toolErrorCode = `http_${res.status}`;
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
              toolOk = false;
              toolErrorCode = 'timeout';
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
          toolOk = false;
          toolErrorCode = 'network';
          const message = err instanceof Error ? err.message : 'tool call failed';
          return { id: fc.id, name: fc.name, response: { error: message } };
        } finally {
          clearTimeout(timeout);
          if (fc.id) toolAbortRef.current.delete(fc.id);
          // Per-call tool telemetry: functionCall received → response ready.
          // Skip cancelled calls (no response is sent for them). A timeout gets a
          // dedicated 'tool_timeout' beacon; every other outcome (success or a
          // client-observed failure) rides the 'tool' beacon with ok/error_code.
          if (!aborted) {
            const tool_ms = Math.round(performance.now() - toolStart);
            if (timedOut) {
              reportMetric({
                event: 'tool_timeout',
                tool_name: fc.name ?? undefined,
                turn_id: toolTurnId,
                tool_ms,
                ok: false,
                error_code: 'timeout',
              });
            } else {
              reportMetric({
                event: 'tool',
                tool_name: fc.name ?? undefined,
                turn_id: toolTurnId,
                tool_ms,
                ok: toolOk,
                error_code: toolErrorCode,
              });
            }
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
  }, [reportMetric, ensureTurnId]);

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
        // A user utterance starts a turn; mint the id now so the transcript row
        // and the turn's events (tool_call, turn_end) share one turn_id.
        optionsRef.current.onTranscript?.({
          role: 'user',
          text: sc.inputTranscription.text,
          final: !!sc.inputTranscription.finished,
          turnId: ensureTurnId(),
        });
      }
      if (sc.outputTranscription?.text) {
        optionsRef.current.onTranscript?.({
          role: 'model',
          text: sc.outputTranscription.text,
          final: !!sc.outputTranscription.finished,
          turnId: turnIdRef.current ?? undefined,
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
    [flushPlayback, enqueuePlayback, handleToolCall, handleToolCancellation, ensureTurnId],
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
      // Close out the session lifecycle. A terminal drop calls emitSessionEnd
      // with 'drop' first (so this no-ops); other failures land as 'error'.
      emitSessionEnd('error');
    },
    [cleanup, setStatus, reportMetric, emitSessionEnd],
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
          // A new utterance begins the moment the model isn't speaking — mint the
          // turn id here so tool calls fired before any audio share it.
          if (firstAudioPendingRef.current) ensureTurnId();
        }

        // Local barge-in: user speaks over the coach. Record it (with the turn it
        // interrupted) BEFORE flushPlayback clears the turn id.
        if (data.rms > BARGE_IN_RMS && statusRef.current === 'speaking') {
          reportMetric({
            event: 'barge_in',
            turn_id: turnIdRef.current ?? undefined,
            turn: turnRef.current,
          });
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
    [flushPlayback, reportMetric, ensureTurnId],
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

      // First open of this session (vs. a mid-session reconnect) — only then do
      // we seed the minutes countdown from the mint response.
      const isFirstOpen = sessionStartRef.current === null;

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
        // Voice minutes exhausted — surface as quota, not a connection error, so
        // the caller can show the "minutes used up" message.
        if (res.status === 429) {
          const detail = await res.json().catch(() => ({}));
          if ((detail as { error?: string })?.error === 'voice_quota_exhausted') {
            const quotaErr = new Error('voice_quota_exhausted');
            (quotaErr as Error & { code?: string }).code = 'voice_quota_exhausted';
            throw quotaErr;
          }
        }
        throw new Error(`Live coach unavailable (${res.status})`);
      }
      const { token, model, promptBytes, remainingSeconds: mintedRemaining } =
        (await res.json()) as {
          token?: string;
          model?: string;
          promptBytes?: number;
          remainingSeconds?: number | null;
        };
      const tokenMs = Math.round(performance.now() - tokenStart);
      if (!token || !model) {
        throw new Error('Invalid live-token response');
      }

      // Seed the local minutes countdown from the mint response (first open only;
      // a reconnect keeps the original countdown anchored to the session start).
      if (isFirstOpen && typeof mintedRemaining === 'number') {
        quotaInitialRef.current = mintedRemaining;
        setRemainingSeconds(mintedRemaining);
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
      // hot path — a fresh turn's TTFA is measured separately. A resume handle
      // means this is a mid-session auto-reconnect, logged distinctly.
      reportMetric({
        event: resumeHandle ? 'reconnect' : 'connect',
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

      // Start the metering/countdown heartbeat (cleared in cleanup on any drop).
      stopHeartbeat();
      heartbeatTimerRef.current = setInterval(
        heartbeatTick,
        VOICE_HEARTBEAT_INTERVAL_MS,
      );
    },
    [
      handleMessage,
      acquireMedia,
      wireCapture,
      setStatus,
      reportMetric,
      stopHeartbeat,
      heartbeatTick,
    ],
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
          if (
            err instanceof Error &&
            (err as Error & { code?: string }).code === 'voice_quota_exhausted'
          ) {
            endForQuotaRef.current();
            return;
          }
          fail(describeError(err, 'Failed to resume live coach'));
        });
        return;
      }

      // No handle (or reconnect already used): terminal. Deliberate stops and
      // already-surfaced errors returned at the top, so reaching here means an
      // unexpected drop we can't recover — surface it instead of going silently
      // idle, so the UI can prompt the user to restart. Mark the lifecycle end
      // as a 'drop' before fail() (whose emitSessionEnd('error') then no-ops).
      emitSessionEnd('drop');
      fail(errMsg ?? 'Live coach disconnected. Please restart to continue.');
    },
    [cleanup, fail, setStatus, openConnection, emitSessionEnd],
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
    // Reset voice-minutes metering for the new session.
    quotaInitialRef.current = null;
    bookedSecondsRef.current = 0;
    setRemainingSeconds(null);

    try {
      await openConnection();
    } catch (err) {
      // Quota exhausted at mint: end gracefully with the "minutes used up"
      // message instead of a generic connection error.
      if (
        err instanceof Error &&
        (err as Error & { code?: string }).code === 'voice_quota_exhausted'
      ) {
        endForQuotaRef.current();
        return;
      }
      // If the mic was granted but connect failed, fail() -> cleanup() stops the
      // held tracks so no mic indicator lingers.
      fail(describeError(err, 'Failed to start live coach'));
    }
  }, [setStatus, openConnection, fail]);

  const disconnect = useCallback(
    (reason: SessionEndReason = 'user_stop') => {
      userStoppedRef.current = true;
      // Guard: a caller wiring disconnect straight to onClick would pass an event
      // here — coerce anything but a known reason back to 'user_stop'.
      const endReason: SessionEndReason =
        reason === 'quota_exhausted' || reason === 'error' || reason === 'drop'
          ? reason
          : 'user_stop';
      // Session-end telemetry (metering 'end' + lifecycle 'session_end'). No-op
      // when no session actually opened.
      emitSessionEnd(endReason);
      cleanup();
      setIsActive(false);
      setRemainingSeconds(null);
      setStatus('idle');
    },
    [cleanup, setStatus, emitSessionEnd],
  );

  // Gracefully end a session because the monthly voice quota ran out. Notify the
  // caller (for the "minutes used up" message) then tear down like a normal stop,
  // tagging the lifecycle end reason as quota exhaustion.
  endForQuotaRef.current = () => {
    optionsRef.current.onQuotaExhausted?.();
    disconnect('quota_exhausted');
  };

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
    remainingSeconds,
  };
}
