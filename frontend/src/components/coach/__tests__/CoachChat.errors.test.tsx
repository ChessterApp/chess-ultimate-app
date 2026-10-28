/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, act, fireEvent } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
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

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
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
});
