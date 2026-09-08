/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

// ---- @google/genai mock ----------------------------------------------------
const g = vi.hoisted(() => ({
  session: {
    sendRealtimeInput: vi.fn(),
    sendClientContent: vi.fn(),
    sendToolResponse: vi.fn(),
    close: vi.fn(),
  },
  connectArgs: { value: null as any },
  connectCalls: [] as any[],
  ctorArgs: { value: null as any },
}));

vi.mock('@google/genai', () => {
  class GoogleGenAI {
    live: { connect: (params: any) => Promise<any> };
    constructor(opts: any) {
      g.ctorArgs.value = opts;
      this.live = {
        connect: vi.fn(async (params: any) => {
          g.connectArgs.value = params;
          g.connectCalls.push(params);
          return g.session;
        }),
      };
    }
  }
  return { GoogleGenAI, Modality: { AUDIO: 'AUDIO' } };
});

import useGeminiLive from '../useGeminiLive';

// ---- Browser API fakes -----------------------------------------------------
const createdSources: any[] = [];
const createdContexts: FakeAudioContext[] = [];
let lastWorkletNode: any = null;
const trackStop = vi.fn();

class FakeAudioContext {
  destination = {};
  currentTime = 0;
  sampleRate: number;
  // iOS starts AudioContexts suspended until resume() runs inside a gesture.
  state: 'suspended' | 'running' | 'closed' = 'suspended';
  audioWorklet = { addModule: vi.fn(async () => {}) };
  resume = vi.fn(async () => {
    this.state = 'running';
  });
  constructor(opts?: { sampleRate?: number }) {
    this.sampleRate = opts?.sampleRate ?? 48000;
    createdContexts.push(this);
  }
  createMediaStreamSource = vi.fn(() => ({ connect: vi.fn() }));
  createBuffer = vi.fn((_ch: number, len: number, rate: number) => ({
    duration: len / rate,
    getChannelData: () => new Float32Array(len),
  }));
  createBufferSource = vi.fn(() => {
    const src = {
      buffer: null as any,
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
      onended: null as null | (() => void),
    };
    createdSources.push(src);
    return src;
  });
  close = vi.fn(async () => {
    this.state = 'closed';
  });
}

class FakeAudioWorkletNode {
  port = { onmessage: null as null | ((ev: MessageEvent) => void), postMessage: vi.fn() };
  connect = vi.fn();
  disconnect = vi.fn();
  constructor() {
    lastWorkletNode = this;
  }
}

function fakeStream(): MediaStream {
  return { getTracks: () => [{ stop: trackStop }] } as unknown as MediaStream;
}

function installBrowserMocks() {
  vi.stubGlobal('AudioContext', FakeAudioContext);
  vi.stubGlobal('AudioWorkletNode', FakeAudioWorkletNode);
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: vi.fn(async () => fakeStream()) },
  });
}

const AUDIO_B64 = btoa(String.fromCharCode(0, 1, 2, 3));

function tokenOk() {
  return vi.fn(async () => ({
    ok: true,
    json: async () => ({
      token: 'auth_tokens/abc',
      model: 'gemini-3.1-flash-live-preview',
      expiresAt: '2026-01-01T00:00:00.000Z',
    }),
  }));
}

beforeEach(() => {
  g.session.sendRealtimeInput.mockReset();
  g.session.sendClientContent.mockReset();
  g.session.sendToolResponse.mockReset();
  g.session.close.mockReset();
  g.connectArgs.value = null;
  g.connectCalls.length = 0;
  g.ctorArgs.value = null;
  createdSources.length = 0;
  createdContexts.length = 0;
  lastWorkletNode = null;
  trackStop.mockReset();
  installBrowserMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useGeminiLive', () => {
  it('reports isSupported=false when AudioWorkletNode is missing', async () => {
    vi.stubGlobal('AudioWorkletNode', undefined);
    const { result } = renderHook(() => useGeminiLive());
    await waitFor(() => expect(result.current.isSupported).toBe(false));
  });

  it('reports isSupported=false when getUserMedia is missing', async () => {
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: undefined,
    });
    const { result } = renderHook(() => useGeminiLive());
    await waitFor(() => expect(result.current.isSupported).toBe(false));
  });

  it('reports isSupported=true when all APIs are present', async () => {
    const { result } = renderHook(() => useGeminiLive());
    await waitFor(() => expect(result.current.isSupported).toBe(true));
  });

  it('connect() posts to the token endpoint, passes the token as apiKey, and connects with the model', async () => {
    const fetchMock = tokenOk();
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useGeminiLive({ getFen: () => 'FEN' }));
    await act(async () => {
      await result.current.connect();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/coach/live-token',
      expect.objectContaining({ method: 'POST' }),
    );
    const body = JSON.parse((fetchMock.mock.calls[0] as any[])[1].body);
    expect(body.fen).toBe('FEN');

    expect(g.ctorArgs.value.apiKey).toBe('auth_tokens/abc');
    expect(g.connectArgs.value.model).toBe('gemini-3.1-flash-live-preview');
    expect(g.connectArgs.value.config.responseModalities).toEqual(['AUDIO']);
    expect(result.current.isActive).toBe(true);
    expect(result.current.status).toBe('listening');
  });

  it('sets status=error and calls onError when the token endpoint fails', async () => {
    const fetchMock = vi.fn(async () => ({ ok: false, status: 401, json: async () => ({}) }));
    vi.stubGlobal('fetch', fetchMock);
    const onError = vi.fn();

    const { result } = renderHook(() => useGeminiLive({ onError }));
    await act(async () => {
      await result.current.connect();
    });

    expect(result.current.status).toBe('error');
    expect(result.current.isActive).toBe(false);
    expect(onError).toHaveBeenCalledOnce();
    expect(g.connectArgs.value).toBeNull(); // no session opened
  });

  it('disconnect() closes the session, stops mic tracks, and is idempotent', async () => {
    vi.stubGlobal('fetch', tokenOk());
    const { result } = renderHook(() => useGeminiLive());
    await act(async () => {
      await result.current.connect();
    });

    act(() => {
      result.current.disconnect();
    });
    expect(g.session.close).toHaveBeenCalledOnce();
    expect(trackStop).toHaveBeenCalled();
    expect(result.current.status).toBe('idle');
    expect(result.current.isActive).toBe(false);

    // Safe to call again.
    expect(() => act(() => result.current.disconnect())).not.toThrow();
  });

  it('barge-in: high-RMS worklet message while speaking flushes playback and returns to listening', async () => {
    vi.stubGlobal('fetch', tokenOk());
    const { result } = renderHook(() => useGeminiLive());
    await act(async () => {
      await result.current.connect();
    });

    // Model sends audio -> status becomes speaking.
    act(() => {
      g.connectArgs.value.callbacks.onmessage({
        serverContent: {
          modelTurn: {
            parts: [{ inlineData: { data: AUDIO_B64, mimeType: 'audio/pcm;rate=24000' } }],
          },
        },
      });
    });
    expect(result.current.status).toBe('speaking');
    expect(createdSources.length).toBe(1);

    // User speaks over the coach -> flush.
    act(() => {
      lastWorkletNode.port.onmessage({ data: { pcm: new ArrayBuffer(4), rms: 0.9 } });
    });

    expect(createdSources[0].stop).toHaveBeenCalled();
    expect(result.current.status).toBe('listening');
  });

  it('sends the initial FEN as a board-update turn immediately after the session opens', async () => {
    vi.stubGlobal('fetch', tokenOk());
    const { result } = renderHook(() => useGeminiLive({ getFen: () => 'INIT_FEN' }));
    await act(async () => {
      await result.current.connect();
    });

    expect(g.session.sendClientContent).toHaveBeenCalledWith({
      turns: [
        {
          role: 'user',
          parts: [{ text: 'Current position (FEN): INIT_FEN' }],
        },
      ],
      turnComplete: false,
    });
  });

  it('sendBoardUpdate() sends the FEN as a non-interrupting client turn when connected', async () => {
    vi.stubGlobal('fetch', tokenOk());
    const { result } = renderHook(() => useGeminiLive({ getFen: () => 'INIT_FEN' }));
    await act(async () => {
      await result.current.connect();
    });
    g.session.sendClientContent.mockClear();

    act(() => {
      result.current.sendBoardUpdate('NEW_FEN');
    });

    expect(g.session.sendClientContent).toHaveBeenCalledTimes(1);
    expect(g.session.sendClientContent).toHaveBeenCalledWith({
      turns: [
        {
          role: 'user',
          parts: [{ text: 'Current position (FEN): NEW_FEN' }],
        },
      ],
      turnComplete: false,
    });
  });

  it('sendBoardUpdate() no-ops safely when no session is connected', () => {
    const { result } = renderHook(() => useGeminiLive({ getFen: () => 'FEN' }));
    expect(() => act(() => result.current.sendBoardUpdate('NEW_FEN'))).not.toThrow();
    expect(g.session.sendClientContent).not.toHaveBeenCalled();
  });

  // ---- Tool bridge (Phase 2) ----------------------------------------------

  // Route fetch: token endpoint -> token; tool endpoint -> supplied handler.
  function routedFetch(toolHandler: (url: string, opts: any) => any) {
    return vi.fn(async (url: string, opts: any) => {
      if (url === '/api/coach/live-token') {
        return {
          ok: true,
          json: async () => ({
            token: 'auth_tokens/abc',
            model: 'gemini-3.1-flash-live-preview',
            expiresAt: '2026-01-01T00:00:00.000Z',
          }),
        };
      }
      return toolHandler(url, opts);
    });
  }

  it('toolCall: proxies each functionCall and replies with sendToolResponse', async () => {
    const toolPayload = {
      result: { ok: true },
      board_actions: [{ type: 'set_fen', fen: 'FEN2' }],
    };
    const fetchMock = routedFetch(() => ({ ok: true, json: async () => toolPayload }));
    vi.stubGlobal('fetch', fetchMock);
    const onToolResult = vi.fn();

    const { result } = renderHook(() =>
      useGeminiLive({ getSessionId: () => 'sess-9', onToolResult }),
    );
    await act(async () => {
      await result.current.connect();
    });

    await act(async () => {
      g.connectArgs.value.callbacks.onmessage({
        toolCall: {
          functionCalls: [{ id: 'c1', name: 'board_control', args: { action_type: 'set_fen' } }],
        },
      });
      await new Promise((r) => setTimeout(r, 0));
    });

    // Proxy was called with the tool name, args and shared session id.
    const toolCall = fetchMock.mock.calls.find((c: any[]) => c[0] === '/api/coach/tool');
    expect(toolCall).toBeTruthy();
    const body = JSON.parse((toolCall as any[])[1].body);
    expect(body).toEqual({
      name: 'board_control',
      args: { action_type: 'set_fen' },
      session_id: 'sess-9',
    });

    expect(g.session.sendToolResponse).toHaveBeenCalledWith({
      functionResponses: [
        { id: 'c1', name: 'board_control', response: { result: { ok: true } } },
      ],
    });
    expect(onToolResult).toHaveBeenCalledWith('board_control', toolPayload);
  });

  it('toolCall: answers every functionCall in one message', async () => {
    const fetchMock = routedFetch(() => ({ ok: true, json: async () => ({ result: 1 }) }));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useGeminiLive());
    await act(async () => {
      await result.current.connect();
    });

    await act(async () => {
      g.connectArgs.value.callbacks.onmessage({
        toolCall: {
          functionCalls: [
            { id: 'a', name: 'tool_a', args: {} },
            { id: 'b', name: 'tool_b', args: {} },
          ],
        },
      });
      await new Promise((r) => setTimeout(r, 0));
    });

    const arg = g.session.sendToolResponse.mock.calls[0][0];
    expect(arg.functionResponses.map((r: any) => r.id).sort()).toEqual(['a', 'b']);
  });

  it('toolCall: sends an error functionResponse when the proxy fetch fails', async () => {
    const fetchMock = routedFetch(() => {
      throw new Error('network down');
    });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useGeminiLive());
    await act(async () => {
      await result.current.connect();
    });

    await act(async () => {
      g.connectArgs.value.callbacks.onmessage({
        toolCall: { functionCalls: [{ id: 'c1', name: 'board_control', args: {} }] },
      });
      await new Promise((r) => setTimeout(r, 0));
    });

    const arg = g.session.sendToolResponse.mock.calls[0][0];
    expect(arg.functionResponses[0].id).toBe('c1');
    expect(arg.functionResponses[0].response.error).toBeTruthy();
  });

  // ---- Session resumption (Phase 3) ---------------------------------------

  const flush = () => new Promise((r) => setTimeout(r, 0));

  it('auto-reconnects once with the captured resumption handle on an unexpected close', async () => {
    vi.stubGlobal('fetch', tokenOk());
    const { result } = renderHook(() => useGeminiLive());
    await act(async () => {
      await result.current.connect();
    });
    const first = g.connectArgs.value;
    expect(g.connectCalls.length).toBe(1);

    // Server issues a resumable handle mid-session.
    act(() => {
      first.callbacks.onmessage({
        sessionResumptionUpdate: { resumable: true, newHandle: 'H1' },
      });
    });

    // Unexpected drop -> reconnect once, passing the handle.
    await act(async () => {
      first.callbacks.onclose();
      await flush();
    });

    expect(g.connectCalls.length).toBe(2);
    expect(g.connectCalls[1].config.sessionResumption).toEqual({ handle: 'H1' });
    expect(result.current.isActive).toBe(true);
    expect(result.current.status).toBe('listening');

    // A second drop must NOT trigger another automatic reconnect; instead the
    // unrecoverable disconnect surfaces as an error state.
    const second = g.connectCalls[1];
    await act(async () => {
      second.callbacks.onclose();
      await flush();
    });
    expect(g.connectCalls.length).toBe(2);
    expect(result.current.status).toBe('error');
  });

  it('surfaces an error (not silent idle) on close when no resumable handle was captured', async () => {
    vi.stubGlobal('fetch', tokenOk());
    const onError = vi.fn();
    const { result } = renderHook(() => useGeminiLive({ onError }));
    await act(async () => {
      await result.current.connect();
    });
    const first = g.connectArgs.value;

    // Non-resumable update carries no usable handle.
    act(() => {
      first.callbacks.onmessage({
        sessionResumptionUpdate: { resumable: false, newHandle: '' },
      });
    });

    await act(async () => {
      first.callbacks.onclose();
      await flush();
    });

    expect(g.connectCalls.length).toBe(1); // no reconnect
    expect(result.current.status).toBe('error');
    expect(result.current.error).toBeTruthy();
    expect(onError).toHaveBeenCalledOnce();
  });

  it('does not auto-reconnect after a deliberate user disconnect', async () => {
    vi.stubGlobal('fetch', tokenOk());
    const { result } = renderHook(() => useGeminiLive());
    await act(async () => {
      await result.current.connect();
    });
    const first = g.connectArgs.value;
    act(() => {
      first.callbacks.onmessage({
        sessionResumptionUpdate: { resumable: true, newHandle: 'H1' },
      });
    });

    // User stops on purpose, then a late close event arrives.
    act(() => {
      result.current.disconnect();
    });
    await act(async () => {
      first.callbacks.onclose();
      await flush();
    });

    expect(g.connectCalls.length).toBe(1); // stayed at the original connect
    expect(result.current.status).toBe('idle');
  });

  it('toolCall: a fetch that never resolves times out at 10s and replies with an error functionResponse', async () => {
    vi.useFakeTimers();
    try {
      // Tool fetch hangs forever, only settling (rejecting) when its signal aborts —
      // exactly how the real fetch behaves under an AbortController timeout.
      const fetchMock = routedFetch((_url, opts) =>
        new Promise((_resolve, reject) => {
          opts.signal.addEventListener('abort', () =>
            reject(new DOMException('aborted', 'AbortError')),
          );
        }),
      );
      vi.stubGlobal('fetch', fetchMock);

      const { result } = renderHook(() => useGeminiLive());
      await act(async () => {
        await result.current.connect();
      });

      act(() => {
        g.connectArgs.value.callbacks.onmessage({
          toolCall: {
            functionCalls: [{ id: 'c1', name: 'analyze_position', args: {} }],
          },
        });
      });

      // The tool never responds; advancing past 10s fires the timeout, which
      // aborts the fetch and forces an error functionResponse.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });

      expect(g.session.sendToolResponse).toHaveBeenCalledTimes(1);
      const arg = g.session.sendToolResponse.mock.calls[0][0];
      expect(arg.functionResponses[0].id).toBe('c1');
      expect(arg.functionResponses[0].response.error).toContain('timed out');
    } finally {
      vi.useRealTimers();
    }
  });

  it('toolCallCancellation: aborts the pending fetch and sends no response', async () => {
    let capturedSignal: AbortSignal | null = null;
    const fetchMock = routedFetch((_url, opts) => {
      capturedSignal = opts.signal;
      return new Promise((_resolve, reject) => {
        opts.signal.addEventListener('abort', () =>
          reject(new DOMException('aborted', 'AbortError')),
        );
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useGeminiLive());
    await act(async () => {
      await result.current.connect();
    });

    await act(async () => {
      g.connectArgs.value.callbacks.onmessage({
        toolCall: { functionCalls: [{ id: 'c1', name: 'board_control', args: {} }] },
      });
      await new Promise((r) => setTimeout(r, 0));
      g.connectArgs.value.callbacks.onmessage({
        toolCallCancellation: { ids: ['c1'] },
      });
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(capturedSignal).not.toBeNull();
    expect((capturedSignal as unknown as AbortSignal).aborted).toBe(true);
    expect(g.session.sendToolResponse).not.toHaveBeenCalled();
  });

  // ---- Mobile gesture / audio-context hardening (voice-mobile-fix) ---------

  it('requests the mic (getUserMedia) BEFORE fetching the live token', async () => {
    const order: string[] = [];
    const gum = vi.fn(async () => {
      order.push('getUserMedia');
      return fakeStream();
    });
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: gum },
    });
    const fetchMock = vi.fn(async (url: string) => {
      order.push(`fetch:${url}`);
      return {
        ok: true,
        json: async () => ({
          token: 'auth_tokens/abc',
          model: 'gemini-3.1-flash-live-preview',
        }),
      };
    });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useGeminiLive());
    await act(async () => {
      await result.current.connect();
    });

    const gumIdx = order.indexOf('getUserMedia');
    const tokenIdx = order.indexOf('fetch:/api/coach/live-token');
    expect(gumIdx).toBeGreaterThanOrEqual(0);
    expect(tokenIdx).toBeGreaterThan(gumIdx);
    // The WS connect only happens after the token fetch, so it is after the mic too.
    expect(g.connectCalls.length).toBe(1);
  });

  it('creates both AudioContexts inside the gesture and resume()s each', async () => {
    vi.stubGlobal('fetch', tokenOk());
    const { result } = renderHook(() => useGeminiLive());
    await act(async () => {
      await result.current.connect();
    });

    // One capture context + one playback context, both resumed off suspended.
    expect(createdContexts.length).toBe(2);
    for (const ctx of createdContexts) {
      expect(ctx.resume).toHaveBeenCalled();
      expect(ctx.state).toBe('running');
    }
  });

  it('prepare() acquires the mic + contexts and is idempotent with connect()', async () => {
    vi.stubGlobal('fetch', tokenOk());
    const { result } = renderHook(() => useGeminiLive());

    await act(async () => {
      await result.current.prepare();
    });
    // Mic + both contexts grabbed by prepare, before any token fetch.
    expect(createdContexts.length).toBe(2);
    expect(result.current.status).toBe('connecting');

    await act(async () => {
      await result.current.connect();
    });
    // connect reused what prepare acquired — no extra contexts spun up.
    expect(createdContexts.length).toBe(2);
    expect(result.current.status).toBe('listening');
  });

  it('prepare() surfaces a blocked-mic DOMException with its name and rejects', async () => {
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn(async () => {
          throw new DOMException('Permission denied', 'NotAllowedError');
        }),
      },
    });
    const onError = vi.fn();
    const { result } = renderHook(() => useGeminiLive({ onError }));

    await act(async () => {
      await expect(result.current.prepare()).rejects.toBeTruthy();
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toContain('NotAllowedError');
    expect(onError).toHaveBeenCalledWith(expect.stringContaining('NotAllowedError'));
  });

  it('stops the held mic tracks when the connection fails after the mic was granted', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === '/api/coach/live-token') {
        return { ok: false, status: 500, json: async () => ({}) };
      }
      return { ok: true, json: async () => ({}) };
    });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useGeminiLive());
    await act(async () => {
      await result.current.connect();
    });

    expect(result.current.status).toBe('error');
    // No leaked mic indicator: the granted stream's tracks were stopped.
    expect(trackStop).toHaveBeenCalled();
  });

  it('includes the actual error detail in the error telemetry event', async () => {
    const metricBodies: any[] = [];
    const fetchMock = vi.fn(async (url: string, opts: any) => {
      if (url === '/api/coach/live-token') {
        return { ok: false, status: 503, json: async () => ({}) };
      }
      if (url === '/api/coach/metrics') {
        metricBodies.push(JSON.parse(opts.body));
      }
      return { ok: true, json: async () => ({}) };
    });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useGeminiLive());
    await act(async () => {
      await result.current.connect();
    });

    const errorMetric = metricBodies.find((m) => m.event === 'error');
    expect(errorMetric).toBeTruthy();
    expect(errorMetric.error).toBeTruthy();
    expect(errorMetric.error).toContain('503');
    // The same detail is exposed to the UI for the visible status pill.
    expect(result.current.error).toContain('503');
  });

  it('reuses the live AudioContexts on reconnect instead of closing/recreating them', async () => {
    vi.stubGlobal('fetch', tokenOk());
    const { result } = renderHook(() => useGeminiLive());
    await act(async () => {
      await result.current.connect();
    });
    expect(createdContexts.length).toBe(2);
    const [captureCtx, playbackCtx] = createdContexts;

    const first = g.connectArgs.value;
    act(() => {
      first.callbacks.onmessage({
        sessionResumptionUpdate: { resumable: true, newHandle: 'H1' },
      });
    });
    await act(async () => {
      first.callbacks.onclose();
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(g.connectCalls.length).toBe(2);
    // No fresh contexts and the originals were never closed — they were reused.
    expect(createdContexts.length).toBe(2);
    expect(captureCtx.close).not.toHaveBeenCalled();
    expect(playbackCtx.close).not.toHaveBeenCalled();
    // The worklet module is only loaded once (re-adding to the same ctx throws).
    expect(captureCtx.audioWorklet.addModule).toHaveBeenCalledTimes(1);
    expect(result.current.status).toBe('listening');
  });

  // ── Voice minutes metering + quota (Task 4) ──────────────────────────────────

  const tokenWithRemaining = (remainingSeconds: number | null) =>
    vi.fn(async (url: string) => {
      if (String(url).includes('/api/coach/live-token')) {
        return {
          ok: true,
          json: async () => ({
            token: 'auth_tokens/abc',
            model: 'gemini-3.1-flash-live-preview',
            remainingSeconds,
          }),
        };
      }
      // The voice-usage heartbeat proxy.
      return { ok: true, json: async () => ({ ok: true }) };
    });

  it('seeds remainingSeconds from the mint response and books a heartbeat every 60s', async () => {
    vi.useFakeTimers();
    let t = 0;
    const nowSpy = vi.spyOn(performance, 'now').mockImplementation(() => t);
    const fetchMock = tokenWithRemaining(1800);
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() =>
      useGeminiLive({ getSessionId: () => 's1' }),
    );
    await act(async () => {
      await result.current.connect();
    });
    expect(result.current.remainingSeconds).toBe(1800);

    // 65s of session elapsed, then the 60s heartbeat interval fires.
    t = 65000;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });

    const hb = fetchMock.mock.calls.find((c: any[]) =>
      String(c[0]).includes('/api/coach/voice-usage'),
    );
    expect(hb).toBeTruthy();
    const body = JSON.parse((hb as any[])[1].body);
    expect(body.session_id).toBe('s1');
    expect(body.seconds_delta).toBe(65);
    expect(result.current.remainingSeconds).toBe(1800 - 65);

    nowSpy.mockRestore();
    vi.useRealTimers();
  });

  it('ends the session and fires onQuotaExhausted when the local countdown hits zero', async () => {
    vi.useFakeTimers();
    let t = 0;
    const nowSpy = vi.spyOn(performance, 'now').mockImplementation(() => t);
    const onQuotaExhausted = vi.fn();
    const fetchMock = tokenWithRemaining(30);
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() =>
      useGeminiLive({ getSessionId: () => 's1', onQuotaExhausted }),
    );
    await act(async () => {
      await result.current.connect();
    });
    expect(result.current.isActive).toBe(true);

    // 40s elapsed > 30s remaining → exhausted on the next tick.
    t = 40000;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });

    expect(onQuotaExhausted).toHaveBeenCalledTimes(1);
    expect(result.current.isActive).toBe(false);
    expect(result.current.status).toBe('idle');

    nowSpy.mockRestore();
    vi.useRealTimers();
  });

  it('surfaces quota exhaustion (not a connection error) when the mint returns 429', async () => {
    const onQuotaExhausted = vi.fn();
    const onError = vi.fn();
    const fetchMock = vi.fn(async () => ({
      ok: false,
      status: 429,
      json: async () => ({ error: 'voice_quota_exhausted', remainingSeconds: 0 }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() =>
      useGeminiLive({ getSessionId: () => 's1', onQuotaExhausted, onError }),
    );
    await act(async () => {
      await result.current.connect();
    });

    expect(onQuotaExhausted).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
    expect(result.current.isActive).toBe(false);
    expect(result.current.status).toBe('idle');
  });

  it('flushes the residual seconds on disconnect', async () => {
    vi.useFakeTimers();
    let t = 0;
    const nowSpy = vi.spyOn(performance, 'now').mockImplementation(() => t);
    const fetchMock = tokenWithRemaining(1800);
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() =>
      useGeminiLive({ getSessionId: () => 's1' }),
    );
    await act(async () => {
      await result.current.connect();
    });

    // Disconnect after 25s with no heartbeat tick yet — the residual is flushed.
    t = 25000;
    act(() => {
      result.current.disconnect();
    });

    const hb = fetchMock.mock.calls.find((c: any[]) =>
      String(c[0]).includes('/api/coach/voice-usage'),
    );
    expect(hb).toBeTruthy();
    expect(JSON.parse((hb as any[])[1].body).seconds_delta).toBe(25);

    nowSpy.mockRestore();
    vi.useRealTimers();
  });

  // ── Phase 2 voice-path instrumentation ───────────────────────────────────────

  // Capture every /api/coach/metrics beacon while serving token + tool responses.
  function metricsCapturingFetch(
    metrics: any[],
    opts?: { tool?: (url: string, o: any) => any; remainingSeconds?: number | null },
  ) {
    return vi.fn(async (url: string, o: any) => {
      const u = String(url);
      if (u.includes('/api/coach/live-token')) {
        return {
          ok: true,
          json: async () => ({
            token: 'auth_tokens/abc',
            model: 'gemini-3.1-flash-live-preview',
            remainingSeconds: opts?.remainingSeconds,
          }),
        };
      }
      if (u.includes('/api/coach/metrics')) {
        metrics.push(JSON.parse(o.body));
        return { ok: true, json: async () => ({}) };
      }
      if (u.includes('/api/coach/tool')) {
        return opts?.tool
          ? opts.tool(url, o)
          : { ok: true, json: async () => ({ result: { ok: true } }) };
      }
      return { ok: true, json: async () => ({ ok: true }) };
    });
  }

  const flushMicro = () => new Promise((r) => setTimeout(r, 0));

  it('tool beacon carries ok=true + a turn_id on a successful call', async () => {
    const metrics: any[] = [];
    vi.stubGlobal('fetch', metricsCapturingFetch(metrics));

    const { result } = renderHook(() =>
      useGeminiLive({ getSessionId: () => 's1' }),
    );
    await act(async () => {
      await result.current.connect();
    });
    await act(async () => {
      g.connectArgs.value.callbacks.onmessage({
        toolCall: { functionCalls: [{ id: 'c1', name: 'analyze_position', args: {} }] },
      });
      await flushMicro();
    });

    const tool = metrics.find((m) => m.event === 'tool');
    expect(tool).toBeTruthy();
    expect(tool.ok).toBe(true);
    expect(tool.tool_name).toBe('analyze_position');
    expect(typeof tool.turn_id).toBe('string');
    expect(tool.turn_id.length).toBeGreaterThan(0);
  });

  it('tool beacon carries ok=false + error_code on a proxy rejection', async () => {
    const metrics: any[] = [];
    vi.stubGlobal(
      'fetch',
      metricsCapturingFetch(metrics, {
        tool: () => ({ ok: false, status: 429, json: async () => ({ error: 'rate' }) }),
      }),
    );

    const { result } = renderHook(() => useGeminiLive());
    await act(async () => {
      await result.current.connect();
    });
    await act(async () => {
      g.connectArgs.value.callbacks.onmessage({
        toolCall: { functionCalls: [{ id: 'c1', name: 'analyze_position', args: {} }] },
      });
      await flushMicro();
    });

    const tool = metrics.find((m) => m.event === 'tool');
    expect(tool).toBeTruthy();
    expect(tool.ok).toBe(false);
    expect(tool.error_code).toBe('http_429');
  });

  it('emits a tool_timeout beacon (not a tool beacon) when the 10s abort fires', async () => {
    vi.useFakeTimers();
    try {
      const metrics: any[] = [];
      vi.stubGlobal(
        'fetch',
        metricsCapturingFetch(metrics, {
          tool: (_url, o) =>
            new Promise((_res, reject) => {
              o.signal.addEventListener('abort', () =>
                reject(new DOMException('aborted', 'AbortError')),
              );
            }),
        }),
      );

      const { result } = renderHook(() => useGeminiLive());
      await act(async () => {
        await result.current.connect();
      });
      act(() => {
        g.connectArgs.value.callbacks.onmessage({
          toolCall: { functionCalls: [{ id: 'c1', name: 'analyze_position', args: {} }] },
        });
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });

      const timeout = metrics.find((m) => m.event === 'tool_timeout');
      expect(timeout).toBeTruthy();
      expect(timeout.error_code).toBe('timeout');
      expect(timeout.ok).toBe(false);
      // A timeout must NOT also emit a plain 'tool' beacon (avoids double-logging).
      expect(metrics.find((m) => m.event === 'tool')).toBeFalsy();
    } finally {
      vi.useRealTimers();
    }
  });

  it('emits a barge_in beacon when local RMS interrupts coach audio', async () => {
    const metrics: any[] = [];
    vi.stubGlobal('fetch', metricsCapturingFetch(metrics));

    const { result } = renderHook(() => useGeminiLive());
    await act(async () => {
      await result.current.connect();
    });
    // Model speaks -> status speaking.
    act(() => {
      g.connectArgs.value.callbacks.onmessage({
        serverContent: {
          modelTurn: {
            parts: [{ inlineData: { data: AUDIO_B64, mimeType: 'audio/pcm;rate=24000' } }],
          },
        },
      });
    });
    expect(result.current.status).toBe('speaking');
    // User speaks over the coach.
    act(() => {
      lastWorkletNode.port.onmessage({ data: { pcm: new ArrayBuffer(4), rms: 0.9 } });
    });

    expect(metrics.find((m) => m.event === 'barge_in')).toBeTruthy();
    expect(result.current.status).toBe('listening');
  });

  it('emits a session_end beacon with end_reason=user_stop on disconnect', async () => {
    const metrics: any[] = [];
    vi.stubGlobal('fetch', metricsCapturingFetch(metrics, { remainingSeconds: null }));

    const { result } = renderHook(() =>
      useGeminiLive({ getSessionId: () => 's1' }),
    );
    await act(async () => {
      await result.current.connect();
    });
    act(() => {
      result.current.disconnect();
    });

    const end = metrics.find((m) => m.event === 'session_end');
    expect(end).toBeTruthy();
    expect(end.end_reason).toBe('user_stop');
    // The metering 'end' beacon is still emitted alongside it.
    expect(metrics.find((m) => m.event === 'end')).toBeTruthy();
  });

  it('reconnect after an unexpected drop emits a reconnect (not connect) beacon', async () => {
    const metrics: any[] = [];
    vi.stubGlobal('fetch', metricsCapturingFetch(metrics));

    const { result } = renderHook(() => useGeminiLive());
    await act(async () => {
      await result.current.connect();
    });
    const first = g.connectArgs.value;
    act(() => {
      first.callbacks.onmessage({
        sessionResumptionUpdate: { resumable: true, newHandle: 'H1' },
      });
    });
    await act(async () => {
      first.callbacks.onclose();
      await flushMicro();
    });

    expect(metrics.filter((m) => m.event === 'connect').length).toBe(1);
    expect(metrics.filter((m) => m.event === 'reconnect').length).toBe(1);
  });

  it('emits session_end with end_reason=quota_exhausted when the countdown hits zero', async () => {
    vi.useFakeTimers();
    let t = 0;
    const nowSpy = vi.spyOn(performance, 'now').mockImplementation(() => t);
    const metrics: any[] = [];
    vi.stubGlobal('fetch', metricsCapturingFetch(metrics, { remainingSeconds: 30 }));

    const { result } = renderHook(() =>
      useGeminiLive({ getSessionId: () => 's1', onQuotaExhausted: vi.fn() }),
    );
    await act(async () => {
      await result.current.connect();
    });
    t = 40000; // exceed the 30s allowance
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });

    const end = metrics.find((m) => m.event === 'session_end');
    expect(end).toBeTruthy();
    expect(end.end_reason).toBe('quota_exhausted');

    nowSpy.mockRestore();
    vi.useRealTimers();
  });
});
