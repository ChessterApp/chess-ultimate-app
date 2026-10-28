/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, act, fireEvent } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import ru from '../../../../messages/ru.json';
import type { UseGeminiLiveReturn, LiveStatus } from '@/hooks/useGeminiLive';

vi.mock('@/hooks/useGeminiLive', () => ({
  __esModule: true,
  default: (): UseGeminiLiveReturn => ({
    status: 'idle' as LiveStatus,
    isSupported: false,
    isActive: false,
    error: null,
    prepare: vi.fn(async () => {}),
    connect: vi.fn(async () => {}),
    prefetch: vi.fn(),
    disconnect: vi.fn(),
    sendBoardUpdate: vi.fn(),
    remainingSeconds: null,
  }),
}));

import CoachChat, { type CoachChatHandle } from '../CoachChat';

// Seam audit 28.10: the proxies' error frames reached the bubble as «Hermes error: 429» / «HTTP 500».
function sse(...frames: unknown[]) {
  return {
    ok: true,
    status: 200,
    body: new ReadableStream({
      start(controller) {
        for (const f of frames) controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(f)}\n\n`));
        controller.close();
      },
    }),
  };
}

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('CoachChat — coach failures in the student language', () => {
  it('shows the rate limit with the wait, not Hermes text', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        sse({ error: 'Rate limit exceeded for free tier. Limit: 30 requests per minute.', error_code: 'rate_limited', rate_limited: true, retry_after: 17 }),
      ),
    );
    render(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <CoachChat currentFen="fen" sessionId="s-1" onBoardActions={() => {}} />
      </NextIntlClientProvider>,
    );
    const input = screen.getByPlaceholderText(en.coach.inputPlaceholder) as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: 'what now?' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    const wanted = en.coach.errorRateLimited.replace('{seconds}', '17');
    expect(await screen.findByText(new RegExp(wanted.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))).toBeTruthy();
    expect(screen.queryByText(/Rate limit exceeded/)).toBeNull();
  });

  it('a game comment the proxy could not get shows a readable line, not «HTTP 500»', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 500, body: null })));
    const ref = React.createRef<CoachChatHandle>();
    render(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <CoachChat ref={ref} currentFen="fen" sessionId="s-1" onBoardActions={() => {}} />
      </NextIntlClientProvider>,
    );
    await act(async () => {
      await ref.current!.streamAssistant('/api/coach/sessions/s-1/game/g1/comment', { event: 'move' });
    });
    expect(screen.queryByText(/HTTP 500/)).toBeNull();
    expect(screen.getByText(new RegExp(en.coach.errorServer.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))).toBeTruthy();
  });

  it('an error frame inside a game comment is worded too', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => sse({ error: 'Game not found', error_code: 'not_found' })));
    const ref = React.createRef<CoachChatHandle>();
    render(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <CoachChat ref={ref} currentFen="fen" sessionId="s-1" onBoardActions={() => {}} />
      </NextIntlClientProvider>,
    );
    await act(async () => {
      await ref.current!.streamAssistant('/api/coach/sessions/s-1/game/g1/comment', { event: 'move' });
    });
    expect(screen.queryByText(/Game not found/)).toBeNull();
    expect(screen.getByText(new RegExp(en.coach.errorNotFound.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))).toBeTruthy();
  });

  // Site review 28.10: Hermes's and the proxies' English texts reached the ru/kz bubble.
  it('a refusal frame in English is shown in the student language', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => sse({ error: 'e9 is not a legal move here.', error_code: 'rejected' })),
    );
    const ref = React.createRef<CoachChatHandle>();
    render(
      <NextIntlClientProvider locale="ru" messages={ru as Record<string, unknown>}>
        <CoachChat ref={ref} currentFen="fen" sessionId="s-1" onBoardActions={() => {}} />
      </NextIntlClientProvider>,
    );
    await act(async () => {
      await ref.current!.streamAssistant('/api/coach/sessions/s-1/game/g1/comment', { event: 'move' });
    });
    expect(screen.queryByText(/legal move/)).toBeNull();
    expect(screen.getByText(new RegExp(esc(ru.coach.errorIllegalMove.replace('{move}', 'e9'))))).toBeTruthy();
  });

  it("the comment proxy's own 401 «Unauthorized» is a sign-in line", async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(401, { error: 'Unauthorized' })));
    const ref = React.createRef<CoachChatHandle>();
    render(
      <NextIntlClientProvider locale="ru" messages={ru as Record<string, unknown>}>
        <CoachChat ref={ref} currentFen="fen" sessionId="s-1" onBoardActions={() => {}} />
      </NextIntlClientProvider>,
    );
    await act(async () => {
      await ref.current!.streamAssistant('/api/coach/sessions/s-1/game/g1/comment', { event: 'move' });
    });
    expect(screen.queryByText(/Unauthorized/)).toBeNull();
    expect(screen.getByText(new RegExp(esc(ru.coach.errorUnauthorized)))).toBeTruthy();
  });

  it('the chat proxy answering 401 is a sign-in line, not «HTTP 401»', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(401, { error: 'Unauthorized' })));
    render(
      <NextIntlClientProvider locale="ru" messages={ru as Record<string, unknown>}>
        <CoachChat currentFen="fen" sessionId="s-1" onBoardActions={() => {}} />
      </NextIntlClientProvider>,
    );
    const input = screen.getByPlaceholderText(ru.coach.inputPlaceholder) as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: 'что дальше?' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    expect(await screen.findByText(new RegExp(esc(ru.coach.errorUnauthorized)))).toBeTruthy();
    expect(screen.queryByText(/HTTP 401|Unauthorized/)).toBeNull();
  });
});

// Site review 28.10: a frozen membership on the game comment showed «У тренера что-то пошло не так» instead of
// going to the upgrade path, as the chat does.
describe('CoachChat — a frozen membership on the game comment', () => {
  const realLocation = window.location;
  afterEach(() => {
    Object.defineProperty(window, 'location', { value: realLocation, writable: true, configurable: true });
  });

  it('goes to the upgrade path and leaves no error bubble', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json(403, { error: 'MEMBERSHIP_RESTRICTED', reason: 'frozen', upgradePath: '/pricing' })),
    );
    const ref = React.createRef<CoachChatHandle>();
    render(
      <NextIntlClientProvider locale="ru" messages={ru as Record<string, unknown>}>
        <CoachChat ref={ref} currentFen="fen" sessionId="s-1" onBoardActions={() => {}} />
      </NextIntlClientProvider>,
    );
    // The redirect is recorded; reads keep the page's URL (next/image builds URLs from it while rendering).
    const assigned: string[] = [];
    const href = realLocation.href;
    const loc = Object.create(realLocation, {
      href: { get: () => href, set: (v: string) => void assigned.push(v), configurable: true },
    });
    Object.defineProperty(window, 'location', { value: loc, writable: true, configurable: true });
    await act(async () => {
      await ref.current!.streamAssistant('/api/coach/sessions/s-1/game/g1/comment', { event: 'move' });
    });
    expect(assigned).toEqual(['/pricing']);
    expect(screen.queryByText(new RegExp(esc(ru.coach.errorServer)))).toBeNull();
    expect(screen.queryByText(new RegExp(esc(ru.coach.errorLabel)))).toBeNull();
  });
});
