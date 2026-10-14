/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, act, fireEvent, waitFor } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import FeedbackButtons from '../FeedbackButtons';
import { feedbackComment } from '../FeedbackSheet';

function renderButtons(props: Partial<React.ComponentProps<typeof FeedbackButtons>> = {}) {
  return render(
    <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
      <FeedbackButtons turnId="turn-1" sessionId="sess-1" {...props} />
    </NextIntlClientProvider>
  );
}

let fetchSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchSpy = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
  global.fetch = fetchSpy as unknown as typeof fetch;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('FeedbackButtons', () => {
  it('renders both thumbs with aria-labels and aria-pressed=false', () => {
    renderButtons();
    const up = screen.getByTestId('feedback-up');
    const down = screen.getByTestId('feedback-down');
    expect(up.getAttribute('aria-label')).toBe(en.coach.feedbackGood);
    expect(down.getAttribute('aria-label')).toBe(en.coach.feedbackBad);
    expect(up.getAttribute('aria-pressed')).toBe('false');
    expect(down.getAttribute('aria-pressed')).toBe('false');
  });

  it('POSTs rating 1 and highlights the up thumb optimistically', async () => {
    renderButtons();
    await act(async () => {
      fireEvent.click(screen.getByTestId('feedback-up'));
    });
    expect(screen.getByTestId('feedback-up').getAttribute('aria-pressed')).toBe('true');
    const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
    expect(body).toEqual({
      turn_id: 'turn-1',
      session_id: 'sess-1',
      rating: 1,
      surface: 'text',
    });
  });

  it('re-clicking the active thumb retracts (rating 0) and clears the highlight', async () => {
    renderButtons();
    await act(async () => {
      fireEvent.click(screen.getByTestId('feedback-up'));
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('feedback-up'));
    });
    expect(screen.getByTestId('feedback-up').getAttribute('aria-pressed')).toBe('false');
    expect(JSON.parse(fetchSpy.mock.calls[1][1].body).rating).toBe(0);
  });

  it('clicking the other thumb switches the verdict', async () => {
    renderButtons();
    await act(async () => {
      fireEvent.click(screen.getByTestId('feedback-up'));
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('feedback-down'));
    });
    expect(screen.getByTestId('feedback-up').getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByTestId('feedback-down').getAttribute('aria-pressed')).toBe('true');
    expect(JSON.parse(fetchSpy.mock.calls[1][1].body).rating).toBe(-1);
  });

  it('reverts the optimistic highlight silently when the POST fails', async () => {
    fetchSpy.mockResolvedValueOnce({ ok: false, status: 502, json: async () => ({}) });
    renderButtons();
    await act(async () => {
      fireEvent.click(screen.getByTestId('feedback-up'));
    });
    await waitFor(() =>
      expect(screen.getByTestId('feedback-up').getAttribute('aria-pressed')).toBe('false')
    );
  });

  it('sends the given surface', async () => {
    renderButtons({ surface: 'review' });
    await act(async () => {
      fireEvent.click(screen.getByTestId('feedback-down'));
    });
    expect(JSON.parse(fetchSpy.mock.calls[0][1].body).surface).toBe('review');
  });

  it('👍 does not open the comment sheet', async () => {
    renderButtons();
    await act(async () => {
      fireEvent.click(screen.getByTestId('feedback-up'));
    });
    expect(screen.queryByTestId('feedback-sheet')).toBeNull();
  });

  it('👎 opens «What went wrong?»; a reason and text re-send the 👎 with a comment', async () => {
    renderButtons();
    await act(async () => {
      fireEvent.click(screen.getByTestId('feedback-down'));
    });
    expect(JSON.parse(fetchSpy.mock.calls[0][1].body)).not.toHaveProperty('comment');
    expect(screen.getByText(en.coach.feedbackSheetTitle)).toBeTruthy();
    const sendButton = screen.getByTestId('feedback-send') as HTMLButtonElement;
    expect(sendButton.disabled).toBe(true);

    fireEvent.click(screen.getByTestId('feedback-reason-wrong'));
    expect(screen.getByTestId('feedback-reason-wrong').getAttribute('aria-pressed')).toBe('true');
    fireEvent.change(screen.getByTestId('feedback-comment'), { target: { value: '  the bishop is on c4 ' } });
    await act(async () => {
      fireEvent.click(sendButton);
    });
    expect(JSON.parse(fetchSpy.mock.calls[1][1].body)).toEqual({
      turn_id: 'turn-1',
      session_id: 'sess-1',
      rating: -1,
      surface: 'text',
      comment: 'wrong: the bishop is on c4',
    });
    expect(screen.queryByTestId('feedback-sheet')).toBeNull();
    expect(screen.getByTestId('feedback-down').getAttribute('aria-pressed')).toBe('true');
  });

  it('skipping or Esc closes the sheet without a second POST', async () => {
    renderButtons();
    await act(async () => {
      fireEvent.click(screen.getByTestId('feedback-down'));
    });
    fireEvent.click(screen.getByText(en.coach.feedbackSkip));
    expect(screen.queryByTestId('feedback-sheet')).toBeNull();
    await act(async () => {
      fireEvent.click(screen.getByTestId('feedback-down')); // retract
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('feedback-down'));
    });
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByTestId('feedback-sheet')).toBeNull();
    expect(fetchSpy.mock.calls.map((c) => JSON.parse(c[1].body).rating)).toEqual([-1, 0, -1]);
  });
});

describe('feedbackComment', () => {
  it('joins the reason code and the words, capped at 500', () => {
    expect(feedbackComment(null, '  ')).toBe('');
    expect(feedbackComment('unclear', '')).toBe('unclear');
    expect(feedbackComment(null, 'too long')).toBe('too long');
    expect(feedbackComment('off_topic', 'x'.repeat(600))).toHaveLength(500);
  });
});
