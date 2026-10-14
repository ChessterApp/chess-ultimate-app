/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';

vi.mock('@/hooks/useGeminiLive', () => ({
  __esModule: true,
  default: () => ({
    status: 'idle',
    isSupported: false,
    isActive: false,
    error: null,
    prepare: vi.fn(),
    connect: vi.fn(),
    prefetch: vi.fn(),
    disconnect: vi.fn(),
    sendBoardUpdate: vi.fn(),
    remainingSeconds: null,
  }),
}));

import CoachChat from '../CoachChat';

const coach = en.coach;
const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

function streamOf(frames: object[]) {
  return vi.fn(async (url: string) => {
    if (String(url) === '/api/coach/chat') {
      return {
        ok: true,
        body: new ReadableStream({
          start(controller) {
            const enc = new TextEncoder();
            for (const f of frames) controller.enqueue(enc.encode(`data: ${JSON.stringify(f)}\n\n`));
            controller.close();
          },
        }),
      };
    }
    return { ok: true, json: async () => ({ messages: [] }) };
  });
}

function renderChat(props: Partial<React.ComponentProps<typeof CoachChat>> = {}) {
  return render(
    <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
      <CoachChat currentFen={START} sessionId="s-1" onBoardActions={() => {}} {...props} />
    </NextIntlClientProvider>,
  );
}

function ask(text: string) {
  const input = screen.getByPlaceholderText(coach.inputPlaceholder);
  fireEvent.change(input, { target: { value: text } });
  fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('CoachChat — rich turn', () => {
  it('shows the starter prompts before the first answer', () => {
    renderChat();
    expect(screen.getByText(coach.promptAnalyze)).toBeTruthy();
  });

  it('renders the quick reaction, the answer below it, the engine card and contextual chips', async () => {
    vi.stubGlobal(
      'fetch',
      streamOf([
        { stage: 'quick' },
        { delta: 'Nice position!' },
        { delta: '\n\n' },
        { stage: 'answer' },
        { tool_call: 'analyze_position' },
        {
          tool_result: {
            tool: 'analyze_position',
            ok: true,
            summary: { kind: 'engine_line', fen: START, eval_cp: 30, depth: 18, lines: [{ san: ['e4', 'e5'], eval_cp: 30 }] },
          },
        },
        { board_actions: [{ type: 'draw_arrows', arrows: [{ from: 'e2', to: 'e4', brush: 'green' }] }] },
        { delta: 'Play **e4**.' },
        { done: true, session_id: 's-1', turn_id: 't-1' },
      ]),
    );
    const onBoardActions = vi.fn();
    renderChat({ onBoardActions });
    ask('What now?');

    const quick = await screen.findByTestId('quick-reaction');
    expect(quick.textContent).toBe('Nice position!');
    const answer = await screen.findByTestId('answer-text');
    expect(answer.textContent).toBe('Play e4.');
    // The reaction stays above the answer, in the same message.
    expect(quick.compareDocumentPosition(answer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    expect(screen.getByTestId('card-engine-line').textContent).toContain('1. e4 e5');
    expect(screen.getByTestId('eval-pill').textContent).toBe('+0.3');
    expect(screen.getByTestId('shown-on-board')).toBeTruthy();

    // Starter prompts give way to chips from the engine line.
    expect(screen.queryByText(coach.promptAnalyze)).toBeNull();
    expect(screen.getByText(coach.chipWhyThisMove)).toBeTruthy();
    expect(screen.getByText(coach.chipAnotherLine)).toBeTruthy();

    onBoardActions.mockClear();
    fireEvent.click(screen.getByTestId('card-engine-show'));
    expect(onBoardActions).toHaveBeenCalledWith([
      { type: 'draw_arrows', arrows: [{ from: 'e2', to: 'e4', brush: 'green' }, { from: 'e7', to: 'e5', brush: 'blue' }] },
    ]);
  });

  it('a turn without stages or summaries renders as before', async () => {
    vi.stubGlobal('fetch', streamOf([{ delta: 'Just text.' }, { done: true, turn_id: 't-2' }]));
    renderChat();
    ask('hi');
    expect((await screen.findByTestId('answer-text')).textContent).toBe('Just text.');
    expect(screen.queryByTestId('quick-reaction')).toBeNull();
    expect(screen.queryByTestId('message-cards')).toBeNull();
    expect(screen.getByText(coach.chipEvaluate)).toBeTruthy();
  });
});
