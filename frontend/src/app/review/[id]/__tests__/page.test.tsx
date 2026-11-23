/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, afterEach, vi } from 'vitest';
import { cleanup, waitFor } from '@testing-library/react';
import { REVIEW_FIXTURE } from '@/components/review/__tests__/fixture';
import { renderIntl } from '@/components/review/__tests__/intl';

let search = new URLSearchParams();
vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'r1' }),
  useSearchParams: () => search,
}));
vi.mock('@/hooks/useDarkMode', () => ({ useDarkMode: () => ({ isDark: false, toggle: () => {} }) }));

vi.mock('@/components/review', async (orig) => {
  const real = await orig<typeof import('@/components/review')>();
  return {
    ...real,
    fetchReview: async () => ({ status: 'done', progress: 100, result: REVIEW_FIXTURE }),
    ReviewBoard: (p: { orientation: string }) => (
      <div data-testid="board" data-orientation={p.orientation} />
    ),
    ReviewSidebar: (p: { userColor?: string }) => (
      <div data-testid="sidebar" data-user-color={p.userColor ?? ''} />
    ),
    EvalBar: () => null,
    EvalGraph: () => null,
    PlaybackControls: () => null,
  };
});

import ReviewPage from '../page';

afterEach(cleanup);

async function renderWith(query: string) {
  search = new URLSearchParams(query);
  const utils = renderIntl(<ReviewPage />);
  await waitFor(() => utils.getByTestId('board'));
  return utils;
}

describe('review page side param', () => {
  it('side=b flips the board and scopes the sidebar to black', async () => {
    const { getByTestId } = await renderWith('source=bot&side=b');
    expect(getByTestId('board').dataset.orientation).toBe('black');
    expect(getByTestId('sidebar').dataset.userColor).toBe('b');
  });

  it('side=w keeps white orientation even if orientation=black was passed', async () => {
    const { getByTestId } = await renderWith('side=w&orientation=black');
    expect(getByTestId('board').dataset.orientation).toBe('white');
    expect(getByTestId('sidebar').dataset.userColor).toBe('w');
  });

  it('without side falls back to orientation and leaves userColor unknown', async () => {
    const { getByTestId } = await renderWith('source=database&orientation=black');
    expect(getByTestId('board').dataset.orientation).toBe('black');
    expect(getByTestId('sidebar').dataset.userColor).toBe('');
  });
});
