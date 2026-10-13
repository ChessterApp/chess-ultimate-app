/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { cleanup, fireEvent, waitFor } from '@testing-library/react';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}));

const startReview = vi.fn();
vi.mock('../reviewApi', () => ({
  startReview: (pgn: string, source?: string) => startReview(pgn, source),
}));

const track = vi.fn();
vi.mock('@/lib/analytics/events', () => ({
  ANALYTICS_EVENTS: { GAME_REVIEW_REQUESTED: 'game_review_requested' },
  track: (...a: unknown[]) => track(...a),
}));

import StartReviewButton, { canReview } from '../StartReviewButton';
import { renderIntl, gameReview } from './intl';

afterEach(() => {
  cleanup();
  push.mockReset();
  startReview.mockReset();
  track.mockReset();
});

describe('canReview (gating rule)', () => {
  it('database games are always reviewable', () => {
    expect(canReview({ isFinished: false }, 'database')).toBe(true);
    expect(canReview({ isFinished: undefined }, 'database')).toBe(true);
  });

  it('bot/online games unlock only when finished', () => {
    expect(canReview({ isFinished: true }, 'bot')).toBe(true);
    expect(canReview({ isFinished: false }, 'bot')).toBe(false);
    expect(canReview({ isFinished: true }, 'online')).toBe(true);
    expect(canReview({ isFinished: false }, 'online')).toBe(false);
  });
});

describe('StartReviewButton', () => {
  it('is disabled with a tooltip for an unfinished bot game', () => {
    const { getByTestId } = renderIntl(
      <StartReviewButton game={{ pgn: '1. e4', isFinished: false }} source="bot" />,
    );
    const btn = getByTestId('start-review-button') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.getAttribute('title')).toBe(gameReview.startButton.disabledTooltip);
  });

  it('starts a review and routes to /review/[id] for a finished game', async () => {
    startReview.mockResolvedValue({ review_id: 'abc123', status: 'queued' });
    const { getByTestId } = renderIntl(
      <StartReviewButton
        game={{ pgn: '1. e4 e5', isFinished: true, orientation: 'black' }}
        source="bot"
      />,
    );
    const btn = getByTestId('start-review-button') as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
    fireEvent.click(btn);
    await waitFor(() => expect(startReview).toHaveBeenCalledWith('1. e4 e5', 'bot'));
    expect(track).toHaveBeenCalledWith('game_review_requested', { source: 'bot' });
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith('/review/abc123?source=bot&orientation=black'),
    );
  });

  it('is enabled for a database game even without isFinished', () => {
    const { getByTestId } = renderIntl(
      <StartReviewButton game={{ pgn: '1. d4' }} source="database" />,
    );
    expect((getByTestId('start-review-button') as HTMLButtonElement).disabled).toBe(false);
  });

  it('surfaces errors via onError instead of navigating', async () => {
    startReview.mockRejectedValue(new Error('boom'));
    const onError = vi.fn();
    const { getByTestId } = renderIntl(
      <StartReviewButton
        game={{ pgn: '1. e4', isFinished: true }}
        source="bot"
        onError={onError}
      />,
    );
    fireEvent.click(getByTestId('start-review-button'));
    await waitFor(() => expect(onError).toHaveBeenCalledWith('boom'));
    expect(push).not.toHaveBeenCalled();
  });
});
