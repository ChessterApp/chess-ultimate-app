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

const trackMock = vi.hoisted(() => vi.fn());
vi.mock('@/lib/analytics/events', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/analytics/events')>()),
  track: trackMock,
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

// The engine line carries a directive for the model (see the hook).
const ENGINE_DIRECTIVE = ' This IS the analysis of the current position: answer from it — do not call analyze_position for this FEN.';

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

  it('connect() uses the token asked for ahead of the tap (one mint)', async () => {
    const fetchMock = tokenOk();
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useGeminiLive({ getFen: () => 'FEN' }));

    act(() => {
      result.current.prefetch();
      result.current.prefetch(); // hover then press: still one request
    });
    await act(async () => {
      await result.current.connect();
    });

    const mints = fetchMock.mock.calls.filter((c) => (c as any[])[0] === '/api/coach/live-token');
    expect(mints).toHaveLength(1);
    expect(g.ctorArgs.value.apiKey).toBe('auth_tokens/abc');
    expect(result.current.isActive).toBe(true);
  });

  it('asks again when the board changed since the early token', async () => {
    const fetchMock = tokenOk();
    vi.stubGlobal('fetch', fetchMock);
    let fen = 'FEN-1';
    const { result } = renderHook(() => useGeminiLive({ getFen: () => fen }));

    act(() => result.current.prefetch());
    fen = 'FEN-2';
    await act(async () => {
      await result.current.connect();
    });

    const bodies = fetchMock.mock.calls
      .filter((c) => (c as any[])[0] === '/api/coach/live-token')
      .map((c) => JSON.parse((c as any[])[1].body).fen);
    expect(bodies).toEqual(['FEN-1', 'FEN-2']);
  });

  it('asks again when the early token failed', async () => {
    let call = 0;
    const fetchMock = vi.fn(async () => {
      call += 1;
      if (call === 1) return { ok: false, status: 502, json: async () => ({}) };
      return {
        ok: true,
        json: async () => ({ token: 'auth_tokens/second', model: 'gemini-3.1-flash-live-preview' }),
      };
    });
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useGeminiLive({ getFen: () => 'FEN' }));

    act(() => result.current.prefetch());
    await act(async () => {
      await result.current.connect();
    });

    expect(g.ctorArgs.value.apiKey).toBe('auth_tokens/second');
    expect(result.current.isActive).toBe(true);
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

  it('transcripts: utterances close at the turn edges when Gemini never marks them finished', async () => {
    // Local run 2026-09-28: no transcription ever came with `finished`, so every
    // utterance of a call merged into one bubble and none reached the history.
    vi.stubGlobal('fetch', tokenOk());
    const onTranscript = vi.fn();
    const { result } = renderHook(() => useGeminiLive({ onTranscript }));
    await act(async () => {
      await result.current.connect();
    });
    const send = (m: unknown) => act(() => g.connectArgs.value.callbacks.onmessage(m));

    send({ serverContent: { inputTranscription: { text: 'Покажи французскую' } } });
    send({ serverContent: { outputTranscription: { text: 'Французская защита' } } });
    send({ serverContent: { outputTranscription: { text: ' — это e4 e6.' } } });
    send({ serverContent: { turnComplete: true } });
    send({ serverContent: { inputTranscription: { text: 'А план?' } } });
    send({ toolCall: { functionCalls: [] } });

    const calls = onTranscript.mock.calls.map(([t]) => `${t.role}:${t.final ? 'final' : 'part'}:${t.text}`);
    expect(calls).toEqual([
      'user:part:Покажи французскую',
      'user:final:', // the coach started answering
      'model:part:Французская защита',
      'model:part: — это e4 e6.',
      'model:final:', // turn complete
      'user:part:А план?',
      'user:final:', // the coach answers with a tool
    ]);
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

    // A click / a cough / an echo spike (one short frame) must not cut the coach off.
    act(() => {
      lastWorkletNode.port.onmessage({ data: { pcm: new ArrayBuffer(4), rms: 0.9 } });
    });
    expect(createdSources[0].stop).not.toHaveBeenCalled();
    expect(result.current.status).toBe('speaking');

    // The user keeps talking over the coach (3 × 100 ms of 16 kHz PCM) -> flush.
    act(() => {
      for (let i = 0; i < 3; i++) {
        lastWorkletNode.port.onmessage({ data: { pcm: new ArrayBuffer(3200), rms: 0.9 } });
      }
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

  // ---- [Engine] line ---------------------------------------------------------

  // Token endpoint -> token; engine-note endpoint -> the supplied handler.
  function engineFetch(noteFor: (fen: string) => Promise<any>) {
    return vi.fn(async (url: string, opts: any) => {
      if (url === '/api/coach/voice/engine-note') {
        return noteFor(JSON.parse(opts.body).fen);
      }
      return {
        ok: true,
        json: async () => ({ token: 'auth_tokens/abc', model: 'gemini-3.8-live' }),
      };
    });
  }
  const noteTurn = (text: string) => ({
    turns: [{ role: 'user', parts: [{ text }] }],
    turnComplete: false,
  });

  // ---- Concept examples the site fetches itself (2026-09-29) --------------

  function conceptFetch(topicResponse: any) {
    return vi.fn(async (url: string, opts: any) => {
      if (url === '/api/coach/tool') {
        return { ok: true, json: async () => topicResponse(JSON.parse(opts.body)) };
      }
      if (url === '/api/coach/voice/engine-note') return { ok: false, status: 404, json: async () => ({}) };
      return { ok: true, json: async () => ({ token: 'auth_tokens/abc', model: 'gemini-3.1-flash-live-preview' }) };
    });
  }
  const PIN = {
    result: {
      title: 'Связка',
      example: { title: 'Слон g5 связывает коня f6 с ферзём d8', fen: 'PIN_FEN', note: 'Конь f6 связан.', side_to_move: 'Black' },
    },
    board_actions: [{ type: 'set_fen', fen: 'PIN_FEN' }],
  };

  it('a concept question puts the knowledge-base example on the board and tells the coach', async () => {
    const fetchMock = conceptFetch(() => PIN);
    vi.stubGlobal('fetch', fetchMock);
    const onToolResult = vi.fn();
    const { result } = renderHook(() => useGeminiLive({ getFen: () => 'F', onToolResult }));
    await act(async () => {
      await result.current.connect();
    });
    const send = (m: unknown) => act(() => g.connectArgs.value.callbacks.onmessage(m));
    send({ serverContent: { inputTranscription: { text: 'Объясни, что такое' } } });
    send({ serverContent: { inputTranscription: { text: ' связка.' } } });

    await waitFor(() => expect(onToolResult).toHaveBeenCalledWith('get_topic', PIN));
    const call = fetchMock.mock.calls.find(([url]) => url === '/api/coach/tool');
    expect(JSON.parse((call as any[])[1].body)).toMatchObject({ name: 'get_topic', args: { topic: 'Объясни, что такое связка.' } });
    const texts = g.session.sendClientContent.mock.calls.map((c: any[]) => c[0].turns[0].parts[0].text);
    expect(texts.some((t: string) => t.startsWith('[Topic]') && t.includes('Слон g5 связывает коня f6') && t.includes('PIN_FEN'))).toBe(true);
    // Once per utterance.
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/coach/tool')).toHaveLength(1);
  });

  it('a question that is not about a concept looks nothing up', async () => {
    const fetchMock = conceptFetch(() => PIN);
    vi.stubGlobal('fetch', fetchMock);
    const onToolResult = vi.fn();
    const { result } = renderHook(() => useGeminiLive({ getFen: () => 'F', onToolResult }));
    await act(async () => {
      await result.current.connect();
    });
    act(() => g.connectArgs.value.callbacks.onmessage({ serverContent: { inputTranscription: { text: 'Что мне здесь играть?' } } }));
    await new Promise((r) => setTimeout(r, 600));
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/coach/tool')).toHaveLength(0);
    expect(onToolResult).not.toHaveBeenCalled();
  });

  it('follows each position with its [Engine] line when Hermes returns one', async () => {
    const fetchMock = engineFetch(async (fen) => ({
      ok: true,
      json: async () => ({ note: `[Engine] ${fen} — Best: d4.` }),
    }));
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useGeminiLive({ getFen: () => 'INIT_FEN' }));
    await act(async () => {
      await result.current.connect();
    });
    await waitFor(() =>
      expect(g.session.sendClientContent).toHaveBeenCalledWith(noteTurn('[Engine] INIT_FEN — Best: d4.' + ENGINE_DIRECTIVE)),
    );

    await act(async () => {
      result.current.sendBoardUpdate('NEW_FEN');
    });
    await waitFor(() =>
      expect(g.session.sendClientContent).toHaveBeenCalledWith(noteTurn('[Engine] NEW_FEN — Best: d4.' + ENGINE_DIRECTIVE)),
    );
    // The same position again is not re-sent (no second engine request).
    const noteCalls = () =>
      fetchMock.mock.calls.filter(([url]) => url === '/api/coach/voice/engine-note').length;
    const before = noteCalls();
    act(() => result.current.sendBoardUpdate('NEW_FEN'));
    expect(noteCalls()).toBe(before);
  });

  it('drops an [Engine] line for a position the board has already left', async () => {
    let releaseFirst: () => void = () => {};
    const fetchMock = engineFetch((fen) =>
      fen === 'INIT_FEN'
        ? new Promise((resolve) => {
            releaseFirst = () => resolve({ ok: true, json: async () => ({ note: '[Engine] stale' }) });
          })
        : Promise.resolve({ ok: false, status: 404, json: async () => ({}) }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useGeminiLive({ getFen: () => 'INIT_FEN' }));
    await act(async () => {
      await result.current.connect();
    });
    act(() => result.current.sendBoardUpdate('NEW_FEN'));
    await act(async () => {
      releaseFirst();
    });

    const texts = g.session.sendClientContent.mock.calls.map((c: any[]) => c[0].turns[0].parts[0].text);
    expect(texts).toEqual(['Current position (FEN): INIT_FEN', 'Current position (FEN): NEW_FEN']);
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

  it('usage beacon relays Gemini usageMetadata with the minted model name', async () => {
    const metrics: any[] = [];
    vi.stubGlobal('fetch', metricsCapturingFetch(metrics));

    const { result } = renderHook(() => useGeminiLive({ getSessionId: () => 's1' }));
    await act(async () => {
      await result.current.connect();
    });
    await act(async () => {
      g.connectArgs.value.callbacks.onmessage({
        usageMetadata: { promptTokenCount: 4200, responseTokenCount: 310, cachedContentTokenCount: 4000 },
      });
      // Zero-token metadata (setup / keepalive frames) must not produce a row.
      g.connectArgs.value.callbacks.onmessage({ usageMetadata: { promptTokenCount: 0 } });
      await flushMicro();
    });

    const usage = metrics.filter((m) => m.event === 'usage');
    expect(usage).toHaveLength(1);
    expect(usage[0]).toMatchObject({
      prompt_tokens: 4200,
      completion_tokens: 310,
      cached_tokens: 4000,
      model: 'gemini-3.1-flash-live-preview',
      sessionId: 's1',
    });
  });

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
    // User speaks over the coach for 300 ms.
    act(() => {
      lastWorkletNode.port.onmessage({ data: { pcm: new ArrayBuffer(9600), rms: 0.9 } });
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

  it('tracks voice_session_started once and voice_session_ended with duration + reason', async () => {
    let t = 0;
    const nowSpy = vi.spyOn(performance, 'now').mockImplementation(() => t);
    vi.stubGlobal('fetch', metricsCapturingFetch([], { remainingSeconds: null }));
    trackMock.mockClear();

    const { result } = renderHook(() => useGeminiLive({ getSessionId: () => 's1' }));
    await act(async () => {
      await result.current.connect();
    });
    expect(trackMock).toHaveBeenCalledWith('voice_session_started', { surface: 'coach' });
    t = 75_400;
    act(() => {
      result.current.disconnect();
    });

    expect(trackMock).toHaveBeenCalledWith('voice_session_ended', {
      surface: 'coach',
      duration_s: 75,
      ended_reason: 'user',
    });
    expect(trackMock.mock.calls.filter((c) => c[0] === 'voice_session_started')).toHaveLength(1);
    nowSpy.mockRestore();
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

// ---- The game, the board lock, the famous games by voice (2026-10-10 / 10-12) ----
describe('useGeminiLive: what the text coach has, by voice', () => {
  const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
  const AFTER = 'rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2';
  const game = (over: Record<string, unknown> = {}) => ({
    board_id: 'b1', student_color: 'white', engine_elo: 1200, comment_mode: 'quiet', status: 'playing',
    result: null, termination: null, winner: null, fen: START, pgn: '', ply: 0, moves: [],
    student_to_move: true, in_check: false, student: null, engine: null, comment_wanted: false, ...over,
  }) as any;
  const AFTER_GAME = game({ fen: AFTER, student: { san: 'e4', uci: 'e2e4', verdict: 'ok', cp_loss: 0, eval_after: 0.3, best: null }, engine: { san: 'd5', uci: 'd7d5' } });

  let toolReply: (body: any) => any = () => ({});
  async function connectWith(opts: Record<string, unknown>) {
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: any) => {
      if (url === '/api/coach/live-token') {
        return { ok: true, json: async () => ({ token: 'auth_tokens/abc', model: 'gemini-3.1-flash-live-preview', expiresAt: '2026-01-01T00:00:00.000Z' }) };
      }
      if (url === '/api/coach/tool') return { ok: true, json: async () => toolReply(JSON.parse(init.body)) };
      return { ok: true, json: async () => ({}) };
    }));
    const hook = renderHook(() => useGeminiLive(opts as any));
    await act(async () => {
      await hook.result.current.connect();
    });
    return hook;
  }
  const fetchCalls = () => (globalThis.fetch as any).mock.calls;
  const bodiesTo = (url: string) => fetchCalls().filter((c: any[]) => c[0] === url).map((c: any[]) => JSON.parse(c[1].body));
  const say = (text: string) => act(() => g.connectArgs.value.callbacks.onmessage({ serverContent: { inputTranscription: { text } } }));
  const call = async (name: string, args: Record<string, unknown>) => {
    await act(async () => {
      g.connectArgs.value.callbacks.onmessage({ toolCall: { functionCalls: [{ id: 'c1', name, args }] } });
      await new Promise((r) => setTimeout(r, 0));
    });
  };
  const sent = () => g.session.sendClientContent.mock.calls.map((c: any[]) => c[0].turns[0].parts[0].text as string);

  it('a game move by the Hermes tool reaches the page, and its board change is not told twice', async () => {
    toolReply = () => ({ result: { ok: true, engine_reply: 'd5' }, board_actions: [{ type: 'game', game: AFTER_GAME }] });
    let current = game();
    const onToolResult = vi.fn();
    const { result } = await connectWith({ getGame: () => current, onToolResult });
    await call('make_game_move', { move: 'e4' });
    expect(onToolResult).toHaveBeenCalledWith('make_game_move', expect.objectContaining({ board_actions: [{ type: 'game', game: AFTER_GAME }] }));
    g.session.sendClientContent.mockClear();
    current = AFTER_GAME;  // the page applied it
    act(() => result.current.sendBoardUpdate(AFTER));
    expect(sent().some((t) => t.startsWith('[Game]'))).toBe(false);
  });

  it("the student's words go with every tool call: Hermes locks the board from them", async () => {
    toolReply = () => ({ result: { ok: true } });
    await connectWith({ getFen: () => START });
    say('Как здесь выиграть?');
    await call('board_control', { action_type: 'set_fen', fen: AFTER });
    expect(bodiesTo('/api/coach/tool').at(-1)).toMatchObject({ name: 'board_control', utterance: 'Как здесь выиграть?' });
  });

  it('a board change in the game goes in as a [Game] line, and the game facts are asked with the session', async () => {
    let current = game();
    const { result } = await connectWith({ getGame: () => current, getSessionId: () => 's1' });
    g.session.sendClientContent.mockClear();
    current = AFTER_GAME;  // the student moved on the board
    act(() => result.current.sendBoardUpdate(AFTER));
    expect(sent().at(-1)).toMatch(/^\[Game\].*the engine answered d5/);
    // Hermes answers with the evaluation and the threat for the game, no best move (as the text coach gets).
    expect(bodiesTo('/api/coach/voice/engine-note').at(-1)).toMatchObject({ fen: AFTER, session_id: 's1' });
  });

  it('a move said in the game is not looked up as an idea', async () => {
    await connectWith({ getGame: () => game(), getFen: () => START });
    vi.useFakeTimers();
    try {
      say('а если Кf3');
      await act(async () => {
        vi.advanceTimersByTime(2000);
      });
    } finally {
      vi.useRealTimers();
    }
    expect(fetchCalls().map((c: any[]) => c[0])).not.toContain('/api/coach/voice/idea');
  });

  it('the idea check gets the game on the board, for «на 8-м ходу»', async () => {
    await connectWith({ getFen: () => START, getPgn: () => '1. e4 e5 2. Nf3' });
    say('а если Кf3');
    await waitFor(() => expect(bodiesTo('/api/coach/voice/idea')).toHaveLength(1));
    expect(bodiesTo('/api/coach/voice/idea')[0]).toMatchObject({ text: 'а если Кf3', pgn: '1. e4 e5 2. Nf3' });
  });

  it('a famous game named: its verified score goes up and the coach gets the facts', async () => {
    toolReply = (body) => (body.name === 'famous_game'
      ? { result: { found: true, facts: '## The famous game … Morphy, ALREADY on the board' }, board_actions: [{ type: 'load_pgn', pgn: '1. e4 e5' }] }
      : { result: {} });
    const onToolResult = vi.fn();
    await connectWith({ getFen: () => START, onToolResult });
    say('Покажи оперную партию Морфи');
    await waitFor(() => expect(onToolResult).toHaveBeenCalledWith('famous_game', expect.anything()));
    expect(bodiesTo('/api/coach/tool')[0]).toMatchObject({ name: 'famous_game', args: { text: 'Покажи оперную партию Морфи' } });
    expect(sent().some((t) => t.startsWith('[Game record]') && t.includes('Morphy'))).toBe(true);
  });

  it('a move said in the game is played by Hermes for the words, and the model gets that result, not a second move', async () => {
    toolReply = (body) => (body.name === 'make_game_move' && body.args.said === 'е4'
      ? { result: { ok: true, student_move: 'e4', engine_reply: 'd5' }, board_actions: [{ type: 'game', game: AFTER_GAME }] }
      : { result: {} });
    const onToolResult = vi.fn();
    await connectWith({ getGame: () => game(), onToolResult });
    say('е4');
    await waitFor(() => expect(onToolResult).toHaveBeenCalledWith('make_game_move', expect.anything()));
    expect(sent().some((t) => t.startsWith("[Game] The student's move e4") && t.includes('the engine answered d5'))).toBe(true);
    await call('make_game_move', { move: 'e4' });  // the model plays it too
    expect(bodiesTo('/api/coach/tool').filter((b: any) => b.name === 'make_game_move')).toHaveLength(1);
    expect(g.session.sendToolResponse.mock.calls.at(-1)[0].functionResponses[0].response.result).toMatchObject({ student_move: 'e4' });
  });

  // Alexander's phone, 23.10: the site's «e4» was still on its way to Hermes when the model called make_game_move
  // for the same «e4»; both reached the game at once and its record broke. The model's call now waits for the
  // site's result instead.
  it("a move the site is still playing is not played a second time by the model's call", async () => {
    let release: (() => void) | null = null;
    toolReply = async (body) => {
      if (body.name === 'make_game_move' && body.args.said === 'е4') {
        await new Promise<void>((r) => { release = r; });
        return { result: { ok: true, student_move: 'e4', engine_reply: 'd5' }, board_actions: [{ type: 'game', game: AFTER_GAME }] };
      }
      return { result: {} };
    };
    const onToolResult = vi.fn();
    await connectWith({ getGame: () => game(), onToolResult });
    say('е4');
    await waitFor(() => expect(bodiesTo('/api/coach/tool').filter((b: any) => b.name === 'make_game_move')).toHaveLength(1));
    const modelCall = call('make_game_move', { move: 'e4' });   // the model, while the site's call is in flight
    await new Promise((r) => setTimeout(r, 10));
    expect(bodiesTo('/api/coach/tool').filter((b: any) => b.name === 'make_game_move')).toHaveLength(1);  // still one
    await act(async () => { release!(); });
    await modelCall;
    await waitFor(() => expect(g.session.sendToolResponse).toHaveBeenCalled());
    expect(bodiesTo('/api/coach/tool').filter((b: any) => b.name === 'make_game_move')).toHaveLength(1);
    expect(g.session.sendToolResponse.mock.calls.at(-1)[0].functionResponses[0].response.result).toMatchObject({ student_move: 'e4' });
    expect(onToolResult).toHaveBeenCalledTimes(1);
  });

  it('a game asked for in words is started by Hermes for the words', async () => {
    toolReply = (body) => (body.name === 'start_game'
      ? { result: { ok: true, student_color: 'black', note: 'The engine opened with e4.' }, board_actions: [{ type: 'game', game: game({ student_color: 'black' }) }] }
      : { result: {} });
    const onToolResult = vi.fn();
    await connectWith({ getGame: () => null, getFen: () => START, onToolResult });
    say('Спорим, я тебя обыграю? Давай сыграем, я чёрными');
    await waitFor(() => expect(onToolResult).toHaveBeenCalledWith('start_game', expect.anything()));
    expect(bodiesTo('/api/coach/tool')[0]).toMatchObject({ name: 'start_game', args: { said: 'Спорим, я тебя обыграю? Давай сыграем, я чёрными' } });
    expect(sent().some((t) => t.startsWith('[Game] The student asked to play') && t.includes('the student plays black'))).toBe(true);
  });

  it('stopping the voice saves what was said so far (open utterances close)', async () => {
    const onTranscript = vi.fn();
    const { result } = await connectWith({ onTranscript });
    act(() => g.connectArgs.value.callbacks.onmessage({ serverContent: { outputTranscription: { text: 'Я отвечаю' } } }));
    act(() => result.current.disconnect());
    expect(onTranscript.mock.calls.map(([t]) => `${t.role}:${t.final}`)).toContain('model:true');
  });

  describe('the notes carry the programme (parity with the text coach, 2026-10-19)', () => {
  it('a puzzle from the programme is said to be its next set, with the address', async () => {
    const { puzzleNote } = await import('../useGeminiLive');
    const note = puzzleNote({ source: 'site_lesson', puzzles: [{ fen: '6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1', solution: ['Ra8#'], lesson: 'Связка — Набор 2', course: 'Тактика', url: 'https://chesster.io/learn/x', n: 1, of: 12, next_in_programme: true }] });
    expect(note).toContain('«Связка — Набор 2»');
    expect(note).toContain('programme continues');
    expect(note).toContain('https://chesster.io/learn/x');
    expect(note).toContain('Ra8#');
  });

  it('«дай три задачи»: the tasks lined up after the one on the board, with their solutions (20.10)', async () => {
    const { puzzleNote } = await import('../useGeminiLive');
    const note = puzzleNote({ source: 'site_lesson', count: 3, on_board: 'site:l1:1', puzzles: [
      { puzzle_id: 'site:l1:1', fen: '6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1', solution: ['Ra8#'], lesson: 'Связка', n: 1, of: 12 },
      { puzzle_id: 'site:l1:2', fen: '8/7p/8/4K2k/7r/7R/6P1/8 w - - 0 1', solution: ['g4#'], lesson: 'Связка', n: 2, of: 12 },
      { puzzle_id: 'site:l2:1', fen: '6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1', solution: ['Ra8#'], lesson: 'Связка. Продолжение', n: 1, of: 9 },
    ] } as Parameters<typeof puzzleNote>[0]);
    expect(note).toContain('2 more tasks are lined up');
    expect(note).toContain('2) task 2 of «Связка», fen 8/7p/8/4K2k/7r/7R/6P1/8 w - - 0 1, solution g4#, puzzle_id site:l1:2');
    expect(note).toContain('3) task 1 of «Связка. Продолжение»');
    expect(note).toContain('board_control set_puzzle');
    const one = puzzleNote({ source: 'site_lesson', puzzles: [{ fen: '6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1', solution: ['Ra8#'], lesson: 'Связка', n: 1, of: 12 }] });
    expect(one).not.toContain('lined up');
  });

  it('a question about the present goes to current_facts and its note reaches the model (20.10)', async () => {
    const { factsNote } = await import('@/lib/coach/voice-game');
    expect(factsNote({ note: '[Facts] ## Verified current facts (Wikipedia, fetched today 2026-10-20) - World Chess Championship: The current world champion is Gukesh Dommaraju…' }))
      .toContain('Gukesh Dommaraju');
    expect(factsNote({ sources: [] })).toBeNull();
    expect(factsNote(null)).toBeNull();
  });

  it("an opening the programme teaches carries the lesson's words", async () => {
    const { openingNote } = await import('../useGeminiLive');
    const note = openingNote({ found: true, name: 'Scotch Game', note: 'Line 1.e4 e5 2.Nf3 Nc6 3.d4.', programme_lesson: { step: 5, lesson: '61', title: 'Шотландская партия', text: 'Шотландская партия относится к открытым дебютам…', parts: [{ title: 'Шотландская Партия (Продолжение)' }] } });
    expect(note).toContain('[Opening] Line 1.e4');
    expect(note).toContain('step 5');
    expect(note).toContain('относится к открытым дебютам');
    expect(note).toContain('(Продолжение)');
  });

  it('a topic of the programme with a game on the board is told from the lesson', async () => {
    const { topicNote } = await import('../useGeminiLive');
    const note = topicNote({ source: 'programme_book', title: 'Русская Партия', programme: { step: 7 }, explanation: 'Русская партия …', game_pgn: '1. e4 e5 2. Nf3 Nf6' });
    expect(note).toContain('step 7');
    expect(note).toContain('writes out is now on the student');
    expect(note).toContain('never from memory');
  });
});

describe('what the words ask for is read by Hermes (POST /api/coach/voice/intent)', () => {
    async function connectAsking(intent: Record<string, unknown>, opts: Record<string, unknown> = {}) {
      vi.stubGlobal('fetch', vi.fn(async (url: string, init?: any) => {
        if (url === '/api/coach/live-token') {
          return { ok: true, json: async () => ({ token: 'auth_tokens/abc', model: 'gemini-3.1-flash-live-preview', expiresAt: '2026-01-01T00:00:00.000Z' }) };
        }
        if (url === '/api/coach/voice/intent') return { ok: true, json: async () => intent };
        if (url === '/api/coach/tool') return { ok: true, json: async () => toolReply(JSON.parse(init.body)) };
        return { ok: true, json: async () => ({}) };
      }));
      const hook = renderHook(() => useGeminiLive(opts as any));
      await act(async () => {
        await hook.result.current.connect();
      });
      return hook;
    }

    it('chunks each marked finished add up to one utterance for the intent call (a Live model may mark every chunk)', async () => {
      // Mock Live run, 2026-10-16: «Хорошо,» [finished] + «e4.» [finished] reached Hermes as «e4.» alone — nothing played.
      toolReply = () => ({ result: { ok: true, student_move: 'e4', engine_reply: 'e5' }, board_actions: [{ type: 'game', game: AFTER_GAME }] });
      await connectAsking({ kind: 'none' }, { getGame: () => game(), getFen: () => START, getSessionId: () => 's1' });
      const asked: string[] = [];
      vi.stubGlobal('fetch', vi.fn(async (url: string, init?: any) => {
        if (url === '/api/coach/voice/intent') {
          const text = JSON.parse(init.body).text as string;
          asked.push(text);
          return { ok: true, json: async () => (text === 'Хорошо, e4.' ? { kind: 'move', san: 'e4' } : { kind: 'none' }) };
        }
        if (url === '/api/coach/tool') return { ok: true, json: async () => toolReply(JSON.parse(init.body)) };
        return { ok: true, json: async () => ({}) };
      }));
      act(() => g.connectArgs.value.callbacks.onmessage({ serverContent: { inputTranscription: { text: 'Хорошо,', finished: true } } }));
      act(() => g.connectArgs.value.callbacks.onmessage({ serverContent: { inputTranscription: { text: ' e4.', finished: true } } }));
      await waitFor(() => expect(bodiesTo('/api/coach/tool').some((b: any) => b.name === 'make_game_move')).toBe(true));
      expect(asked.at(-1)).toBe('Хорошо, e4.');
      expect(bodiesTo('/api/coach/tool').find((b: any) => b.name === 'make_game_move')).toMatchObject({ args: { move: 'e4' }, utterance: 'Хорошо, e4.' });
    });

    it('a refused move is told to the model and to the page, never «played» by talking', async () => {
      toolReply = () => ({ result: { error: "'e4' is not a legal move here.", board: 'Nothing was played and the game did not change.' } });
      const onToolFailure = vi.fn();
      await connectAsking({ kind: 'move', san: 'e4' }, { getGame: () => game(), getFen: () => START, onToolFailure });
      say('Хорошо, e4.');
      await waitFor(() => expect(onToolFailure).toHaveBeenCalledWith('make_game_move', "'e4' is not a legal move here."));
      expect(sent().some((t) => t.startsWith('[Game]') && t.includes('no move was played') && t.includes('not a legal move'))).toBe(true);
    });

    it('with no session yet, the voice asks the page for one before the intent and the tool calls', async () => {
      toolReply = () => ({ result: { ok: true, student_color: 'white', note: 'The game is on.' }, board_actions: [{ type: 'game', game: game() }] });
      let sid: string | null = null;
      const ensureSession = vi.fn(async () => { sid = 's-new'; return sid; });
      await connectAsking({ kind: 'game_request', color: 'white', elo: null }, { getFen: () => START, getGame: () => null, getSessionId: () => sid, ensureSession });
      say('Давай сыграем');
      await waitFor(() => expect(bodiesTo('/api/coach/tool').some((b: any) => b.name === 'start_game')).toBe(true));
      expect(ensureSession).toHaveBeenCalled();
      expect(bodiesTo('/api/coach/voice/intent')[0].session_id).toBe('s-new');
      expect(bodiesTo('/api/coach/tool').find((b: any) => b.name === 'start_game').session_id).toBe('s-new');
    });

    it('«Дай мне тактическую задачу» fetches a puzzle, the gate copy missed it', async () => {
      toolReply = () => ({ result: { puzzles: [{ fen: START, solution: ['e4'] }] }, board_actions: [] });
      await connectAsking({ kind: 'puzzle', theme: null }, { getFen: () => START });
      say('Дай мне тактическую задачу');
      await waitFor(() => expect(bodiesTo('/api/coach/tool').some((b: any) => b.name === 'get_puzzle')).toBe(true));
      expect(bodiesTo('/api/coach/voice/intent')[0]).toMatchObject({ text: 'Дай мне тактическую задачу' });
    });

    it('«Сдаюсь, покажи решение» puts the verified solution on the board and hands the model the exact line (23.10)', async () => {
      toolReply = (body) => (body.name === 'puzzle_solution'
        ? { result: { ok: true, line: '24...Qf3+ 25.Kg1 Nh3#', moves: ['Qf3+', 'Kg1', 'Nh3#'], note: 'The solution is SHOWN on the board with arrows. Say it EXACTLY, move by move: 24...Qf3+ 25.Kg1 Nh3#.' },
            board_actions: [{ type: 'draw_arrows', arrows: [{ from: 'f6', to: 'f3', brush: 'green' }] }] }
        : { result: {} });
      const onToolResult = vi.fn();
      await connectAsking({ kind: 'solution' }, { getFen: () => '3rkr2/1Qpb4/p1B1pq2/7p/3PN1p1/B1P3P1/P4nKP/R4R2 b - - 3 24', onToolResult });
      say('Сдаюсь, покажи решение');
      await waitFor(() => expect(onToolResult).toHaveBeenCalledWith('puzzle_solution', expect.objectContaining({ board_actions: [{ type: 'draw_arrows', arrows: [{ from: 'f6', to: 'f3', brush: 'green' }] }] })));
      expect(bodiesTo('/api/coach/tool').find((b: any) => b.name === 'puzzle_solution')).toMatchObject({ args: {}, utterance: 'Сдаюсь, покажи решение' });
      expect(sent().some((t) => t.startsWith('[Puzzle]') && t.includes('24...Qf3+ 25.Kg1 Nh3#'))).toBe(true);
      await call('puzzle_solution', {});   // the model asks for it too: the site's result, no second call
      expect(bodiesTo('/api/coach/tool').filter((b: any) => b.name === 'puzzle_solution')).toHaveLength(1);
    });

    it('a move Hermes read from the words is played as that move', async () => {
      toolReply = () => ({ result: { ok: true, student_move: 'Bc4', engine_reply: 'Nf6' }, board_actions: [{ type: 'game', game: AFTER_GAME }] });
      await connectAsking({ kind: 'move', san: 'Bc4' }, { getGame: () => game(), getFen: () => START });
      say('слон си четыре');
      await waitFor(() => expect(bodiesTo('/api/coach/tool').some((b: any) => b.name === 'make_game_move')).toBe(true));
      expect(bodiesTo('/api/coach/tool').find((b: any) => b.name === 'make_game_move')).toMatchObject({ args: { move: 'Bc4' } });
    });

    it('a question about the board in front of the student fetches nothing', async () => {
      await connectAsking({ kind: 'board' }, { getFen: () => AFTER });
      say('Почему здесь связка?');
      await waitFor(() => expect(bodiesTo('/api/coach/voice/intent')).toHaveLength(1));
      await new Promise((r) => setTimeout(r, 50));
      expect(bodiesTo('/api/coach/tool').filter((b: any) => b.name === 'get_topic')).toHaveLength(0);
    });
  });
});
