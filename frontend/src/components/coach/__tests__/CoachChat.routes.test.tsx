/**
 * @vitest-environment jsdom
 */
/**
 * The text coach's seam, driven end to end (28.10): the REAL CoachChat (and its FeedbackButtons),
 * fetch routed into the REAL Next route handlers, only Hermes (HERMES_URL) stubbed. The chat turn,
 * a voice transcript written back to the session and a thumbs-up are checked against Hermes's
 * request models (hermes_contract.json); see seam-harness.ts. The voice hook is mocked here: its
 * own seam is useGeminiLive.routes.test.ts.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, act, fireEvent, waitFor } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import { CLEAN, createHarness, defaultHermesReply, hermesBody, seamProblems, HERMES, type Harness } from '@/app/api/coach/__tests__/seam-harness';

vi.mock('next/server', async (orig) => ({ ...(await orig<typeof import('next/server')>()), after: () => {} }));
vi.mock('@clerk/nextjs/server', () => ({ auth: async () => ({ userId: 'u1' }) }));
vi.mock('@/lib/coach-access', () => ({ requireCoachAccess: async () => null }));
vi.mock('@/lib/require-api-access', () => ({ requireApiAccess: async () => null }));
vi.mock('@/lib/subscription-tier', () => ({ resolveUserTier: async () => 'pro' }));
vi.mock('@/lib/analytics/server', () => ({ captureServer: () => {} }));

const live = vi.hoisted(() => ({
  options: null as null | { onTranscript?: (t: { role: 'user' | 'model'; text: string; final: boolean; turnId?: string }) => void },
}));
vi.mock('@/hooks/useGeminiLive', () => ({
  __esModule: true,
  default: (options: typeof live.options) => {
    live.options = options;
    return {
      status: 'idle', isSupported: true, isActive: false, error: null, remainingSeconds: null,
      prepare: async () => {}, connect: async () => {}, prefetch: () => {}, disconnect: () => {}, sendBoardUpdate: () => {},
    };
  },
}));

vi.stubEnv('HERMES_URL', HERMES);

import CoachChat from '../CoachChat';

const FEN = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1';
let h: Harness;

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  h = createHarness({ cookie: 'NEXT_LOCALE=ru' });
  vi.stubGlobal('fetch', vi.fn(h.fetch));
});

afterEach(async () => {
  await h.settled();
  expect(h.problems()).toEqual({});
  cleanup();
  vi.unstubAllGlobals();
});

function renderChat() {
  return render(
    <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
      <CoachChat currentFen={FEN} sessionId="s1" boardId="b1" onBoardActions={() => {}} />
    </NextIntlClientProvider>,
  );
}
const sse = (...frames: unknown[]) =>
  new Response(frames.map((f) => `data: ${JSON.stringify(f)}\n\n`).join(''), { headers: { 'content-type': 'text/event-stream' } });
const atHermes = (path: string) => {
  const call = h.to(path).at(-1);
  expect(call, `the page never called ${path}`).toBeDefined();
  expect(seamProblems(call!)).toEqual(CLEAN);
  return { sent: call!.sent, hermes: hermesBody(call!) };
};

describe('text coach seam through the real proxies: what the page sends and Hermes reads reaches Hermes', () => {
  it('chat turn, then 👍 on its answer: both reach Hermes whole', async () => {
    h.reply = (path) => (path === '/api/coach/chat'
      ? sse({ delta: 'Играйте e5.' }, { done: true, session_id: 's1', turn_id: 't1' })
      : defaultHermesReply(path));
    renderChat();
    const input = screen.getByPlaceholderText(en.coach.inputPlaceholder);
    fireEvent.change(input, { target: { value: 'что тут играть?' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    await waitFor(() => expect(h.to('/api/coach/chat')).toHaveLength(1));
    expect(atHermes('/api/coach/chat')).toMatchObject({
      sent: { message: 'что тут играть?', fen: FEN, session_id: 's1', board_id: 'b1' },
      hermes: { message: 'что тут играть?', fen: FEN, session_id: 's1', board_id: 'b1', locale: 'ru' },
    });

    const up = await screen.findByTestId('feedback-up');
    await act(async () => {
      fireEvent.click(up);
    });
    await waitFor(() => expect(h.to('/api/coach/feedback')).toHaveLength(1));
    expect(atHermes('/api/coach/feedback')).toMatchObject({
      sent: { turn_id: 't1', session_id: 's1', rating: 1, surface: 'text' },
      hermes: { turn_id: 't1', session_id: 's1', rating: 1, surface: 'text' },
    });
  });

  it('a final voice utterance is written to the session with its time and turn id', async () => {
    renderChat();
    await act(async () => {
      live.options?.onTranscript?.({ role: 'user', text: 'атакуй короля', final: true, turnId: 'vt1' });
    });
    await waitFor(() => expect(h.to('/api/coach/sessions/s1/messages')).toHaveLength(1));
    expect(atHermes('/api/coach/sessions/s1/messages')).toMatchObject({
      sent: { role: 'user', content: 'атакуй короля', source: 'voice', turn_id: 'vt1' },
      hermes: { role: 'user', content: 'атакуй короля', source: 'voice', turn_id: 'vt1', client_ts: expect.any(String) },
    });
  });
});
