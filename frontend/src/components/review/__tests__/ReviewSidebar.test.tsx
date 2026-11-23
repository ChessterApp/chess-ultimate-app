/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, afterEach, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import ReviewSidebar, { coachCopy } from '../ReviewSidebar';
import { reviewReducer } from '../reviewStore';
import { REVIEW_FIXTURE } from './fixture';
import { renderIntl } from './intl';
import ru from '../../../../messages/ru.json';
import type { ReviewResult } from '../types';

vi.mock('next/image', () => ({ default: () => null }));

afterEach(cleanup);

/** Echo translator: key + values, so assertions see exactly what was passed. */
const t = (key: string, values?: Record<string, string | number>) =>
  `${key} ${JSON.stringify(values ?? {})}`;

/** Bot played white at 100%, user (black) at 12.9; bot had the brilliancy. */
const BOT_WON: ReviewResult = {
  ...REVIEW_FIXTURE,
  accuracy: { w: 100, b: 12.9 },
  tally: {
    w: { ...REVIEW_FIXTURE.tally.w, brilliant: 2, blunder: 0 },
    b: { ...REVIEW_FIXTURE.tally.b, brilliant: 0, blunder: 3 },
  },
};

describe('coachCopy', () => {
  it('speaks only about the user’s side when the colour is known', () => {
    const user = { ...BOT_WON, accuracy: { w: 12.9, b: 100 }, tally: { w: BOT_WON.tally.b, b: BOT_WON.tally.w } };
    const copy = coachCopy(t, user, 'w');
    expect(copy.message).toContain('coach.messages.review ');
    expect(copy.message).toContain('12.9');
    expect(copy.message).not.toContain('100');
  });

  it('uses only the user’s tallies (no brilliancy credit for the bot’s moves)', () => {
    const copy = coachCopy(t, BOT_WON, 'b');
    expect(copy.headline).toBe('coach.headlines.review {}');
    expect(copy.message).toBe('coach.messages.review {"accuracy":"12.9"}');
  });

  it('stays neutral without a known colour — no "best" accuracy praise', () => {
    const copy = coachCopy(t, BOT_WON);
    expect(copy.message).toContain('coach.messages.brilliantNeutral');
    const clean = coachCopy(t, {
      ...BOT_WON,
      tally: { w: { ...BOT_WON.tally.w, brilliant: 0 }, b: { ...BOT_WON.tally.b, brilliant: 0, blunder: 0 } },
    });
    expect(clean.message).toBe('coach.messages.cleanNeutral {"white":"100.0","black":"12.9"}');
    expect(clean.message).not.toContain('best');
  });
});

describe('ReviewSidebar', () => {
  const props = {
    mode: 'highlights' as const,
    white: { name: 'White' },
    black: { name: 'Black' },
    onStartReview: () => {},
    currentPly: 0,
    onSetPly: () => {},
    onExitReview: () => {},
  };

  it('renders "your accuracy" with the user’s number, never the bot’s 100', () => {
    const data = { ...BOT_WON, accuracy: { w: 12.9, b: 100 }, tally: { w: BOT_WON.tally.b, b: BOT_WON.tally.w } };
    const { getByTestId } = renderIntl(<ReviewSidebar {...props} data={data} userColor="w" />);
    const text = getByTestId('coach-intro').textContent ?? '';
    expect(text).toContain('Your accuracy was 12.9%');
    expect(text).not.toContain('100');
  });

  it('localizes the opening name for ru and says "Твоя точность"', () => {
    const data = {
      ...BOT_WON,
      opening: { eco: 'B20', name: 'Sicilian Defense: Bowdler Attack', lastBookPly: 2 },
    };
    const { getByTestId } = render(
      <NextIntlClientProvider locale="ru" messages={ru as Record<string, unknown>}>
        <ReviewSidebar {...props} data={data} userColor="b" />
      </NextIntlClientProvider>,
    );
    const text = getByTestId('coach-intro').textContent ?? '';
    expect(text).toContain('Сицилианская защита: Bowdler Attack');
    expect(text).not.toContain('Sicilian Defense');
    expect(text).toContain('Твоя точность — 12.9%');
  });
});

describe('reviewReducer setMode', () => {
  const base = { reviewId: 'r', data: REVIEW_FIXTURE, currentPly: 6, mode: 'highlights' as const };

  it('entering review mode starts at ply 0', () => {
    expect(reviewReducer(base, { type: 'setMode', mode: 'review' }).currentPly).toBe(0);
  });

  it('leaving review mode keeps the current ply', () => {
    const inReview = { ...base, mode: 'review' as const, currentPly: 3 };
    expect(reviewReducer(inReview, { type: 'setMode', mode: 'highlights' }).currentPly).toBe(3);
  });
});
