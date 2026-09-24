/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, act, fireEvent } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import type { UseGeminiLiveReturn, LiveStatus } from '@/hooks/useGeminiLive';

// ── Mock the Gemini Live hook: capture the options it was called with, and
//    return a state object each test can configure. ───────────────────────────
const live = vi.hoisted(() => ({
  options: null as null | {
    getFen?: () => string;
    getSessionId?: () => string | null | undefined;
    onTranscript?: (t: { role: 'user' | 'model'; text: string; final: boolean }) => void;
  },
  ret: null as unknown as UseGeminiLiveReturn,
}));

vi.mock('@/hooks/useGeminiLive', () => ({
  __esModule: true,
  default: (options: typeof live.options) => {
    live.options = options;
    return live.ret;
  },
}));

import CoachChat from '../CoachChat';

function makeReturn(overrides: Partial<UseGeminiLiveReturn> = {}): UseGeminiLiveReturn {
  return {
    status: 'idle' as LiveStatus,
    isSupported: true,
    isActive: false,
    error: null,
    prepare: vi.fn(async () => {}),
    connect: vi.fn(async () => {}),
    disconnect: vi.fn(),
    sendBoardUpdate: vi.fn(),
    remainingSeconds: null,
    ...overrides,
  };
}

function renderChat(currentFen = 'startpos-fen') {
  return render(
    <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
      <CoachChat
        currentFen={currentFen}
        sessionId={null}
        onBoardActions={() => {}}
      />
    </NextIntlClientProvider>
  );
}

const coach = en.coach;

beforeEach(() => {
  live.options = null;
  live.ret = makeReturn();
  // jsdom does not implement scrollIntoView (called on message updates).
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(cleanup);

describe('CoachChat voice mode', () => {
  it('renders the mic button when voice is supported', () => {
    live.ret = makeReturn({ isSupported: true });
    renderChat();
    expect(screen.getByTestId('voice-toggle')).toBeTruthy();
  });

  it('hides the mic button when voice is not supported', () => {
    live.ret = makeReturn({ isSupported: false });
    renderChat();
    expect(screen.queryByTestId('voice-toggle')).toBeNull();
  });

  it('calls connect() when clicking the mic while idle', async () => {
    const connect = vi.fn(async () => {});
    live.ret = makeReturn({ status: 'idle', isActive: false, connect });
    // Voice ensures a session first; stub that call so connect is reached.
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: 'sess-new' }),
    }) as unknown as typeof fetch;
    renderChat();
    await act(async () => {
      fireEvent.click(screen.getByTestId('voice-toggle'));
    });
    expect(connect).toHaveBeenCalledTimes(1);
  });

  it('calls disconnect() when clicking the mic while active', () => {
    const disconnect = vi.fn();
    live.ret = makeReturn({ status: 'listening', isActive: true, disconnect });
    renderChat();
    fireEvent.click(screen.getByTestId('voice-toggle'));
    expect(disconnect).toHaveBeenCalledTimes(1);
  });

  it('shows remaining voice minutes while active', () => {
    // 1600s → ceil(1600/60) = 27 min left.
    live.ret = makeReturn({ status: 'listening', isActive: true, remainingSeconds: 1600 });
    renderChat();
    const label = screen.getByTestId('voice-minutes-left');
    expect(label.textContent).toContain('27 min left');
    // Above the 5-min threshold → not the warning styling.
    expect(label.className).not.toContain('amber');
  });

  it('warns (amber) when ≤5 minutes remain', () => {
    live.ret = makeReturn({ status: 'listening', isActive: true, remainingSeconds: 180 });
    renderChat();
    const label = screen.getByTestId('voice-minutes-left');
    expect(label.textContent).toContain('3 min left');
    expect(label.className).toContain('amber');
  });

  it('does not show the minutes label when remaining is unknown (null)', () => {
    live.ret = makeReturn({ status: 'listening', isActive: true, remainingSeconds: null });
    renderChat();
    expect(screen.queryByTestId('voice-minutes-left')).toBeNull();
  });

  it('shows the "minutes used up" banner after the quota is exhausted', () => {
    live.ret = makeReturn({ status: 'idle', isActive: false });
    renderChat();
    expect(screen.queryByTestId('voice-quota-pill')).toBeNull();
    // The hook fires onQuotaExhausted when minutes run out.
    act(() => {
      (live.options as { onQuotaExhausted?: () => void })?.onQuotaExhausted?.();
    });
    const banner = screen.getByTestId('voice-quota-pill');
    expect(banner.textContent).toContain('text chat is unlimited');
  });

  it('shows the listening pill when status is listening', () => {
    live.ret = makeReturn({ status: 'listening', isActive: true });
    renderChat();
    expect(screen.getByTestId('voice-pill').textContent).toBe(coach.voiceListening);
  });

  it('shows the speaking pill when status is speaking', () => {
    live.ret = makeReturn({ status: 'speaking', isActive: true });
    renderChat();
    expect(screen.getByTestId('voice-pill').textContent).toBe(coach.voiceSpeaking);
  });

  it('renders a user bubble from a final transcript', () => {
    renderChat();
    act(() => {
      live.options?.onTranscript?.({ role: 'user', text: 'hello coach', final: true });
    });
    expect(screen.getByText('hello coach')).toBeTruthy();
  });

  it('updates the same bubble across streaming chunks instead of creating two', () => {
    renderChat();
    act(() => {
      live.options?.onTranscript?.({ role: 'model', text: 'Let me ', final: false });
    });
    act(() => {
      live.options?.onTranscript?.({ role: 'model', text: 'think.', final: true });
    });
    // Both chunks land in one bubble: no separate 'Let me ' node survives.
    expect(screen.queryByText('Let me ')).toBeNull();
    expect(screen.getByText('Let me think.')).toBeTruthy();
  });

  it('surfaces the error message as the mic tooltip in the error state', () => {
    live.ret = makeReturn({ status: 'error', error: 'Mic blocked' });
    renderChat();
    const btn = screen.getByTestId('voice-toggle');
    expect(btn.getAttribute('title')).toBe('Mic blocked');
    expect(btn.getAttribute('data-status')).toBe('error');
  });

  it('shows a visible error pill with the error text and a retry hint (not only the tooltip)', () => {
    live.ret = makeReturn({ status: 'error', error: 'NotAllowedError: blocked' });
    renderChat();
    const pill = screen.getByTestId('voice-pill');
    expect(pill.textContent).toContain('NotAllowedError: blocked');
    expect(pill.textContent).toContain(coach.voiceRetryHint);
  });

  it('falls back to the generic voice-error label when no error string is present', () => {
    live.ret = makeReturn({ status: 'error', error: null });
    renderChat();
    const pill = screen.getByTestId('voice-pill');
    expect(pill.textContent).toContain(coach.voiceError);
    expect(pill.textContent).toContain(coach.voiceRetryHint);
  });

  it('acquires the mic (prepare) before creating the session and connecting', async () => {
    const callOrder: string[] = [];
    const prepare = vi.fn(async () => {
      callOrder.push('prepare');
    });
    const connect = vi.fn(async () => {
      callOrder.push('connect');
    });
    live.ret = makeReturn({ status: 'idle', isActive: false, prepare, connect });
    global.fetch = vi.fn(async () => {
      callOrder.push('fetch:session');
      return { ok: true, json: async () => ({ id: 'sess-new' }) };
    }) as unknown as typeof fetch;

    renderChat();
    await act(async () => {
      fireEvent.click(screen.getByTestId('voice-toggle'));
    });

    expect(callOrder).toEqual(['prepare', 'fetch:session', 'connect']);
  });

  it('does not create a session or connect when mic prepare fails', async () => {
    const prepare = vi.fn(async () => {
      throw new DOMException('Permission denied', 'NotAllowedError');
    });
    const connect = vi.fn(async () => {});
    live.ret = makeReturn({ status: 'idle', isActive: false, prepare, connect });
    const fetchSpy = vi.fn(async (_url?: string) => ({
      ok: true,
      json: async () => ({ id: 'x' }),
    }));
    global.fetch = fetchSpy as unknown as typeof fetch;

    renderChat();
    await act(async () => {
      fireEvent.click(screen.getByTestId('voice-toggle'));
    });

    expect(prepare).toHaveBeenCalledTimes(1);
    expect(connect).not.toHaveBeenCalled();
    const createCall = fetchSpy.mock.calls.find(([url]) =>
      String(url).endsWith('/api/coach/sessions')
    );
    expect(createCall).toBeFalsy();
  });

  it('passes the live FEN through getFen', () => {
    renderChat();
    expect(live.options?.getFen?.()).toBe('startpos-fen');
  });
});

describe('CoachChat shared conversation memory', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    });
    global.fetch = fetchSpy as unknown as typeof fetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function renderChatWithSession(sessionId: string | null) {
    return render(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <CoachChat currentFen="fen" sessionId={sessionId} onBoardActions={() => {}} />
      </NextIntlClientProvider>
    );
  }

  it('exposes the current session id to the voice hook via getSessionId', () => {
    renderChatWithSession('sess-42');
    expect(live.options?.getSessionId?.()).toBe('sess-42');
  });

  it('persists a finalized user transcript to the shared session as voice', async () => {
    renderChatWithSession('sess-1');
    await act(async () => {
      live.options?.onTranscript?.({ role: 'user', text: 'attack the king', final: true });
    });

    const call = fetchSpy.mock.calls.find(([url]) =>
      String(url).includes('/api/coach/sessions/sess-1/messages')
    );
    expect(call).toBeTruthy();
    const [, opts] = call!;
    expect(opts.method).toBe('POST');
    const sent = JSON.parse(opts.body);
    expect(sent).toEqual({
      role: 'user',
      content: 'attack the king',
      source: 'voice',
      client_ts: expect.any(String),
    });
  });

  it('persists a finalized coach transcript as assistant/voice', async () => {
    renderChatWithSession('sess-1');
    await act(async () => {
      live.options?.onTranscript?.({ role: 'model', text: 'Open lines first.', final: true });
    });

    const call = fetchSpy.mock.calls.find(([url]) =>
      String(url).includes('/api/coach/sessions/sess-1/messages')
    );
    const sent = JSON.parse(call![1].body);
    expect(sent).toEqual({
      role: 'assistant',
      content: 'Open lines first.',
      source: 'voice',
      client_ts: expect.any(String),
    });
  });

  it('does NOT persist interim (non-final) transcripts', async () => {
    renderChatWithSession('sess-1');
    await act(async () => {
      live.options?.onTranscript?.({ role: 'user', text: 'thinking...', final: false });
    });
    const call = fetchSpy.mock.calls.find(([url]) =>
      String(url).includes('/api/coach/sessions/sess-1/messages')
    );
    expect(call).toBeFalsy();
  });

  it('persists the full accumulated utterance across streamed chunks', async () => {
    renderChatWithSession('sess-1');
    await act(async () => {
      live.options?.onTranscript?.({ role: 'model', text: 'Let me ', final: false });
    });
    await act(async () => {
      live.options?.onTranscript?.({ role: 'model', text: 'think.', final: true });
    });
    const call = fetchSpy.mock.calls.find(([url]) =>
      String(url).includes('/api/coach/sessions/sess-1/messages')
    );
    const sent = JSON.parse(call![1].body);
    expect(sent.content).toBe('Let me think.');
  });

  it('does not persist transcripts when there is no session id', async () => {
    renderChatWithSession(null);
    await act(async () => {
      live.options?.onTranscript?.({ role: 'user', text: 'orphan', final: true });
    });
    const call = fetchSpy.mock.calls.find(([url]) =>
      String(url).includes('/messages')
    );
    expect(call).toBeFalsy();
  });

  it('creates a session before connecting voice when none exists', async () => {
    const onSessionCreated = vi.fn();
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: 'new-sess' }),
    });
    const connect = vi.fn(async () => {});
    live.ret = makeReturn({ status: 'idle', isActive: false, connect });

    render(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <CoachChat
          currentFen="fen"
          sessionId={null}
          onBoardActions={() => {}}
          onSessionCreated={onSessionCreated}
        />
      </NextIntlClientProvider>
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId('voice-toggle'));
    });

    const createCall = fetchSpy.mock.calls.find(
      ([url, opts]) =>
        String(url).endsWith('/api/coach/sessions') && opts?.method === 'POST'
    );
    expect(createCall).toBeTruthy();
    expect(onSessionCreated).toHaveBeenCalledWith('new-sess');
    expect(connect).toHaveBeenCalledTimes(1);
  });

  it('reuses the existing session id (no create) when one is present', async () => {
    const connect = vi.fn(async () => {});
    live.ret = makeReturn({ status: 'idle', isActive: false, connect });

    renderChatWithSession('existing');
    await act(async () => {
      fireEvent.click(screen.getByTestId('voice-toggle'));
    });

    const createCall = fetchSpy.mock.calls.find(
      ([url, opts]) =>
        String(url).endsWith('/api/coach/sessions') && opts?.method === 'POST'
    );
    expect(createCall).toBeFalsy();
    expect(connect).toHaveBeenCalledTimes(1);
  });
});

describe('CoachChat voice tool results', () => {
  function renderChatWithBoardActions(onBoardActions: (a: unknown[]) => void) {
    return render(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <CoachChat
          currentFen="fen"
          sessionId="sess-1"
          onBoardActions={onBoardActions as never}
        />
      </NextIntlClientProvider>
    );
  }

  it('applies board_actions from a voice tool result through onBoardActions', () => {
    const onBoardActions = vi.fn();
    renderChatWithBoardActions(onBoardActions);

    const actions = [{ type: 'set_fen', fen: 'FEN_FROM_TOOL' }];
    act(() => {
      (live.options as { onToolResult?: (n: string, r: unknown) => void })?.onToolResult?.(
        'board_control',
        { result: {}, board_actions: actions }
      );
    });

    expect(onBoardActions).toHaveBeenCalledWith(actions);
  });

  it('renders game-search results returned from a voice tool call', () => {
    const onBoardActions = vi.fn();
    renderChatWithBoardActions(onBoardActions);

    const games = [
      {
        id: 'g1',
        white_name: 'Carlsen',
        black_name: 'Nakamura',
        result: '1-0',
        date: '2021',
        eco: 'C65',
      },
    ];
    act(() => {
      (live.options as { onToolResult?: (n: string, r: unknown) => void })?.onToolResult?.(
        'search_master_games',
        { result: games, board_actions: [] }
      );
    });

    expect(screen.getByText('Carlsen')).toBeTruthy();
    expect(screen.getByText('Nakamura')).toBeTruthy();
  });

  it('ignores a malformed tool result without throwing', () => {
    const onBoardActions = vi.fn();
    renderChatWithBoardActions(onBoardActions);
    expect(() =>
      act(() => {
        (live.options as { onToolResult?: (n: string, r: unknown) => void })?.onToolResult?.(
          'x',
          null
        );
      })
    ).not.toThrow();
    expect(onBoardActions).not.toHaveBeenCalled();
  });
});

describe('CoachChat board sync', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('pushes a debounced board update when the FEN changes while voice is active', () => {
    const sendBoardUpdate = vi.fn();
    live.ret = makeReturn({ status: 'listening', isActive: true, sendBoardUpdate });

    const { rerender } = renderChat('fen-1');
    // Initial FEN must not be re-sent — the session anchors it on open.
    act(() => vi.advanceTimersByTime(300));
    expect(sendBoardUpdate).not.toHaveBeenCalled();

    rerender(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <CoachChat currentFen="fen-2" sessionId={null} onBoardActions={() => {}} />
      </NextIntlClientProvider>
    );

    // Debounced: nothing yet before the timer fires.
    expect(sendBoardUpdate).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(300));
    expect(sendBoardUpdate).toHaveBeenCalledTimes(1);
    expect(sendBoardUpdate).toHaveBeenCalledWith('fen-2');
  });

  it('does not push board updates when voice is inactive', () => {
    const sendBoardUpdate = vi.fn();
    live.ret = makeReturn({ status: 'idle', isActive: false, sendBoardUpdate });

    const { rerender } = renderChat('fen-1');
    rerender(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <CoachChat currentFen="fen-2" sessionId={null} onBoardActions={() => {}} />
      </NextIntlClientProvider>
    );
    act(() => vi.advanceTimersByTime(300));
    expect(sendBoardUpdate).not.toHaveBeenCalled();
  });
});

describe('CoachChat — persisted sessions and boards', () => {
  it('restores the session history from the server when restoreHistory is set', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes('/api/coach/sessions/s-42/messages')) {
        return {
          ok: true,
          json: async () => ({
            messages: [
              { role: 'user', content: 'что тут играть?', timestamp: 1700000000, source: 'text' },
              { role: 'assistant', content: 'Начни с центра.', timestamp: 1700000010, source: 'text' },
            ],
          }),
        };
      }
      return { ok: true, json: async () => ({}) };
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <CoachChat currentFen="fen" sessionId="s-42" restoreHistory onBoardActions={() => {}} />
      </NextIntlClientProvider>,
    );
    expect(await screen.findByText('что тут играть?')).toBeTruthy();
    expect(await screen.findByText('Начни с центра.')).toBeTruthy();
    vi.unstubAllGlobals();
  });

  it('sends board_id with every chat turn', async () => {
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (String(url) === '/api/coach/chat') {
        return {
          ok: true,
          body: new ReadableStream({
            start(controller) {
              controller.enqueue(new TextEncoder().encode('data: {"done": true, "session_id": "s-1", "active_board_id": "b-9"}\n\n'));
              controller.close();
            },
          }),
        };
      }
      return { ok: true, json: async () => ({ messages: [] }) };
    });
    vi.stubGlobal('fetch', fetchMock);
    const onActive = vi.fn();

    render(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <CoachChat currentFen="fen" sessionId="s-1" boardId="b-9" onBoardActions={() => {}} onActiveBoardChanged={onActive} />
      </NextIntlClientProvider>,
    );
    const input = screen.getByPlaceholderText(coach.inputPlaceholder) as HTMLTextAreaElement | HTMLInputElement;
    fireEvent.change(input, { target: { value: 'покажи' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) => String(u) === '/api/coach/chat');
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call![1]?.body)).board_id).toBe('b-9');
    });
    await vi.waitFor(() => expect(onActive).toHaveBeenCalledWith('b-9'));
    vi.unstubAllGlobals();
  });
});

describe('CoachChat — pasted games go straight to the board', () => {
  it('classifies PGN, FEN and plain questions', async () => {
    const { classifyPastedText } = await import('../CoachChat');
    expect(classifyPastedText('1. e4 e5 2. Nf3 Nc6 3. Bb5 a6')).toBe('pgn');
    expect(classifyPastedText('[Event "x"]\n\n1. d4 d5 2. c4 e6 1-0')).toBe('pgn');
    expect(classifyPastedText('rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1')).toBe('fen');
    expect(classifyPastedText('что играть после 1. e4?')).toBeNull();
    expect(classifyPastedText('')).toBeNull();
  });

  it('loads a pasted PGN onto the board without a model call', () => {
    const onBoardActions = vi.fn();
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <CoachChat currentFen="fen" sessionId={null} onBoardActions={onBoardActions} />
      </NextIntlClientProvider>,
    );
    const input = screen.getByPlaceholderText(coach.inputPlaceholder);
    fireEvent.paste(input, { clipboardData: { getData: () => '1. e4 e5 2. Nf3 Nc6 3. Bb5 a6' } });
    expect(onBoardActions).toHaveBeenCalledWith([{ type: 'load_pgn', pgn: '1. e4 e5 2. Nf3 Nc6 3. Bb5 a6' }]);
    expect(screen.getByText(coach.loadedPgn)).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('classifies Lichess and Chess.com game links', async () => {
    const { classifyPastedText } = await import('../CoachChat');
    expect(classifyPastedText('https://lichess.org/kAdOQKeh')).toBe('url');
    expect(classifyPastedText('https://lichess.org/kAdOQKeh/black#23')).toBe('url');
    expect(classifyPastedText('lichess.org/kAdOQKehAbCd')).toBe('url');
    expect(classifyPastedText('https://www.chess.com/game/live/184239477800')).toBe('url');
    expect(classifyPastedText('https://www.chess.com/analysis/game/live/184239477800?tab=review')).toBe('url');
    expect(classifyPastedText('https://lichess.org/@/DrNykterstein')).toBeNull();
    expect(classifyPastedText('https://chesster.io/coach')).toBeNull();
  });

  it('loads a pasted game link through /api/coach/import-url', async () => {
    const onBoardActions = vi.fn();
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ pgn: '1. e4 e5 *', white: 'Hikaru', black: 'alexrustemov' }),
    }));
    vi.stubGlobal('fetch', fetchMock);
    render(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <CoachChat currentFen="fen" sessionId={null} onBoardActions={onBoardActions} />
      </NextIntlClientProvider>,
    );
    const input = screen.getByPlaceholderText(coach.inputPlaceholder);
    fireEvent.paste(input, { clipboardData: { getData: () => 'https://www.chess.com/game/live/184239477800' } });
    await vi.waitFor(() => expect(onBoardActions).toHaveBeenCalledWith([{ type: 'load_pgn', pgn: '1. e4 e5 *' }]));
    expect(fetchMock).toHaveBeenCalledWith('/api/coach/import-url', expect.objectContaining({ method: 'POST' }));
    expect(screen.getByText('Loaded the game from the link: Hikaru — alexrustemov.')).toBeTruthy();
    vi.unstubAllGlobals();
  });

  it('shows the reason when a link cannot be loaded', async () => {
    const onBoardActions = vi.fn();
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 400, json: async () => ({ error: 'Lichess does not know this game' }) })));
    render(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <CoachChat currentFen="fen" sessionId={null} onBoardActions={onBoardActions} />
      </NextIntlClientProvider>,
    );
    fireEvent.paste(screen.getByPlaceholderText(coach.inputPlaceholder), { clipboardData: { getData: () => 'https://lichess.org/aaaaaaaa' } });
    await vi.waitFor(() => expect(screen.getByText('Could not load the game from the link: Lichess does not know this game')).toBeTruthy());
    expect(onBoardActions).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});

describe('CoachChat — a photo of the board or a scoresheet', () => {
  function pngFile() {
    return new File([new Uint8Array([137, 80, 78, 71])], 'board.png', { type: 'image/png' });
  }

  it('board photo → /api/convert-image → set_fen', async () => {
    const onBoardActions = vi.fn();
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ fen: '8/8/8/4k3/8/8/8/4K2R w - - 0 1' }) }));
    vi.stubGlobal('fetch', fetchMock);
    render(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <CoachChat currentFen="fen" sessionId={null} onBoardActions={onBoardActions} />
      </NextIntlClientProvider>,
    );
    fireEvent.click(screen.getByLabelText(coach.attachPhoto));
    fireEvent.click(screen.getByText(coach.photoToPosition));
    const input = screen.getByTestId('photo-input') as HTMLInputElement;
    await act(async () => {
      fireEvent.change(input, { target: { files: [pngFile()] } });
    });
    await vi.waitFor(() => expect(onBoardActions).toHaveBeenCalledWith([{ type: 'set_fen', fen: '8/8/8/4k3/8/8/8/4K2R w - - 0 1' }]));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/convert-image');
    expect(JSON.parse(String(init.body))).toHaveProperty('image');
    expect(screen.getByText(coach.loadedFromPhoto)).toBeTruthy();
    vi.unstubAllGlobals();
  });

  it('scoresheet photo → /api/convert-scoresheet → load_pgn', async () => {
    const onBoardActions = vi.fn();
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ pgn: '1. d4 d5 *' }) }));
    vi.stubGlobal('fetch', fetchMock);
    render(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <CoachChat currentFen="fen" sessionId={null} onBoardActions={onBoardActions} />
      </NextIntlClientProvider>,
    );
    fireEvent.click(screen.getByLabelText(coach.attachPhoto));
    fireEvent.click(screen.getByText(coach.scoresheetToGame));
    await act(async () => {
      fireEvent.change(screen.getByTestId('photo-input'), { target: { files: [pngFile()] } });
    });
    await vi.waitFor(() => expect(onBoardActions).toHaveBeenCalledWith([{ type: 'load_pgn', pgn: '1. d4 d5 *' }]));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/convert-scoresheet');
    expect(JSON.parse(String(init.body)).images).toHaveLength(1);
    expect(screen.getByText(coach.loadedFromScoresheet)).toBeTruthy();
    vi.unstubAllGlobals();
  });

  it('shows the reason when recognition fails', async () => {
    const onBoardActions = vi.fn();
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 429, json: async () => ({ error: 'rate_limited' }) })));
    render(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <CoachChat currentFen="fen" sessionId={null} onBoardActions={onBoardActions} />
      </NextIntlClientProvider>,
    );
    fireEvent.click(screen.getByLabelText(coach.attachPhoto));
    fireEvent.click(screen.getByText(coach.photoToPosition));
    await act(async () => {
      fireEvent.change(screen.getByTestId('photo-input'), { target: { files: [pngFile()] } });
    });
    await vi.waitFor(() => expect(screen.getByText('Could not recognize the photo: rate_limited')).toBeTruthy());
    expect(onBoardActions).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});

describe('CoachChat — own and imported games as cards', () => {
  it('renders a source caption and opens a card that carries its PGN', async () => {
    const onOpenGame = vi.fn();
    const frames = [
      'data: {"delta": "Вот твои партии."}\n\n',
      'data: {"game_results": [{"id": "uuid-1", "white_name": "me", "black_name": "you", "result": "1-0", "date": "2026-09-20", "eco": "C50", "opening": "", "event": "Club", "white_elo": 1500, "black_elo": 1400, "source": "user", "pgn": "1. e4 e5 1-0"}]}\n\n',
      'data: {"done": true, "session_id": "s1", "turn_id": "t1"}\n\n',
    ];
    const encoder = new TextEncoder();
    let i = 0;
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      status: 200,
      body: {
        getReader: () => ({
          read: async () => (i < frames.length ? { done: false, value: encoder.encode(frames[i++]) } : { done: true, value: undefined }),
        }),
      },
    })));
    render(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <CoachChat currentFen="fen" sessionId={null} onBoardActions={vi.fn()} onOpenGame={onOpenGame} />
      </NextIntlClientProvider>,
    );
    const input = screen.getByPlaceholderText(coach.inputPlaceholder);
    fireEvent.change(input, { target: { value: 'покажи мои партии' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    await vi.waitFor(() => expect(screen.getByText('me')).toBeTruthy());
    expect(screen.getByText(coach.sourceUser)).toBeTruthy();
    fireEvent.click(screen.getByText('me'));
    expect(onOpenGame).toHaveBeenCalledWith(expect.objectContaining({ id: 'uuid-1', source: 'user', pgn: '1. e4 e5 1-0' }));
    vi.unstubAllGlobals();
  });
});
