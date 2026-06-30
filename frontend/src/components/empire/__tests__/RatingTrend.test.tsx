/**
 * @vitest-environment jsdom
 *
 * Client-component tests for RatingTrend. Mocks next-intl + the branding
 * context so we don't need a full <OrganizationProvider> tree.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render } from '@testing-library/react';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/contexts/OrganizationContext', () => ({
  useBranding: () => ({ primaryColor: '#9333ea' }),
}));

import RatingTrend from '../RatingTrend';
import type { CERatingPoint } from '@/lib/chess-empire-client';

afterEach(() => {
  cleanup();
});

describe('RatingTrend', () => {
  it('renders SVG with one circle per point', () => {
    const points: CERatingPoint[] = [
      { date: '2026-05-01', rating: 1100 },
      { date: '2026-05-10', rating: 1150 },
      { date: '2026-05-20', rating: 1200 },
      { date: '2026-05-30', rating: 1230 },
    ];
    const { getAllByTestId, getByTestId } = render(<RatingTrend points={points} />);
    expect(getByTestId('empire-rating-svg')).toBeTruthy();
    expect(getAllByTestId('empire-rating-point')).toHaveLength(4);
    expect(getByTestId('empire-rating-current').textContent).toBe('1230');
  });

  it('renders empty-state copy when no points', () => {
    const { getByTestId, queryByTestId } = render(<RatingTrend points={[]} />);
    expect(getByTestId('empire-rating-empty')).toBeTruthy();
    expect(queryByTestId('empire-rating-svg')).toBeNull();
  });

  it('renders positive delta with `+` sign', () => {
    const points: CERatingPoint[] = [
      { date: '2026-05-01', rating: 1000 },
      { date: '2026-05-30', rating: 1150 },
    ];
    const { getByTestId } = render(<RatingTrend points={points} />);
    expect(getByTestId('empire-rating-delta').textContent).toContain('+150');
  });

  it('renders negative delta with `−` sign', () => {
    const points: CERatingPoint[] = [
      { date: '2026-05-01', rating: 1200 },
      { date: '2026-05-30', rating: 1100 },
    ];
    const { getByTestId } = render(<RatingTrend points={points} />);
    const delta = getByTestId('empire-rating-delta').textContent || '';
    expect(delta).toContain('−');
    expect(delta).toContain('100');
  });

  it('renders zero delta with `±`', () => {
    const points: CERatingPoint[] = [
      { date: '2026-05-01', rating: 1200 },
      { date: '2026-05-30', rating: 1200 },
    ];
    const { getByTestId } = render(<RatingTrend points={points} />);
    expect(getByTestId('empire-rating-delta').textContent).toContain('±');
  });
});
