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
    expect(sent).toEqual({ role: 'user', content: 'attack the king', source: 'voice' });
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
