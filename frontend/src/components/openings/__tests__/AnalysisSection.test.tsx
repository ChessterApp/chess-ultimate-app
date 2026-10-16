// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import React from 'react';
import type { UserGame } from '@/hooks/useUserGames';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, unknown>) =>
    params && 'count' in params ? `${key}:${params.count}` : key,
  useLocale: () => 'en',
}));

import AnalysisSection, { formatEdited, summarizeLine } from '../AnalysisSection';

function makeVariation(i: number, overrides: Partial<UserGame> = {}): UserGame {
  return {
    id: `v${i}`, user_id: 'u', title: `Line ${i}`, white: '?', black: '?',
    white_elo: null, black_elo: null, result: '*', date: null, event: 'Variation',
    eco: null, opening_name: null, pgn: '1. e4 c5 2. Nf3 d6 *', notes: null, tags: [],
    is_favorite: false, source: 'board_entry',
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

const four = [1, 2, 3, 4].map((i) => makeVariation(i));

function renderSection(props: Partial<React.ComponentProps<typeof AnalysisSection>> = {}) {
  const handlers = {
    onPageChange: vi.fn(),
    onOpenGame: vi.fn(),
  };
  render(
    <AnalysisSection
      games={four}
      total={four.length}
      page={1}
      perPage={20}
      loading={false}
      {...handlers}
      {...props}
    />,
  );
  return handlers;
}

afterEach(() => cleanup());

describe('AnalysisSection', () => {
  it('renders the header count and the top 3 rows with moves and ply count', () => {
    renderSection();
    expect(screen.getByText('myGames.analysis')).toBeTruthy();
    expect(screen.getByText('4')).toBeTruthy();
    expect(screen.getByText('Line 1')).toBeTruthy();
    expect(screen.getByText('Line 3')).toBeTruthy();
    expect(screen.queryByText('Line 4')).toBeNull();
    expect(screen.getAllByText('1. e4 c5 2. Nf3 d6')).toHaveLength(3);
    expect(screen.getAllByText(/^myGames\.plyCount:4/)).toHaveLength(3);
  });

  it('falls back to the untitled label', () => {
    renderSection({ games: [makeVariation(1, { title: null })], total: 1 });
    expect(screen.getByText('myGames.untitledVariation')).toBeTruthy();
  });

  it('"Show all" reveals every row and "Show less" collapses back', () => {
    renderSection();
    fireEvent.click(screen.getByText('myGames.showAll:4'));
    expect(screen.getByText('Line 4')).toBeTruthy();
    fireEvent.click(screen.getByText('myGames.showLess'));
    expect(screen.queryByText('Line 4')).toBeNull();
  });

  it('paginates the full list once expanded', () => {
    const { onPageChange } = renderSection({ total: 45 });
    fireEvent.click(screen.getByText('myGames.showAll:45'));
    fireEvent.click(screen.getByRole('button', { name: 'Go to page 2' }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it('hides "Show all" when everything already fits', () => {
    renderSection({ games: four.slice(0, 2), total: 2 });
    expect(screen.queryByText(/myGames\.showAll/)).toBeNull();
  });

  it('collapses and expands from the header', () => {
    renderSection();
    const header = screen.getByRole('button', { name: /myGames\.analysis/ });
    expect(header.getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(header);
    expect(header.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByText('Line 1')).toBeNull();
    fireEvent.click(header);
    expect(screen.getByText('Line 1')).toBeTruthy();
  });

  it('starts collapsed when defaultOpen is false', () => {
    renderSection({ defaultOpen: false });
    expect(screen.queryByText('Line 1')).toBeNull();
  });

  it('shows its own empty state', () => {
    renderSection({ games: [], total: 0 });
    expect(screen.getByText('myGames.noAnalysis')).toBeTruthy();
  });

  it('opens a game on row click', () => {
    const { onOpenGame } = renderSection();
    fireEvent.click(screen.getByText('Line 2'));
    expect(onOpenGame).toHaveBeenCalledWith(four[1]);
  });

  it('Add variation button calls its handler; hidden without one', () => {
    const onAddVariation = vi.fn();
    renderSection({ onAddVariation });
    fireEvent.click(screen.getByText('myGames.addVariation'));
    expect(onAddVariation).toHaveBeenCalledTimes(1);
    cleanup();
    renderSection();
    expect(screen.queryByText('myGames.addVariation')).toBeNull();
  });

  it('edit/delete call their handlers without opening the row', () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const { onOpenGame } = renderSection({ onEdit, onDelete });
    fireEvent.click(screen.getAllByLabelText('edit game')[0]);
    fireEvent.click(screen.getAllByLabelText('delete game')[0]);
    expect(onEdit.mock.calls[0][1]).toBe(four[0]);
    expect(onDelete.mock.calls[0][1]).toBe(four[0]);
    expect(onOpenGame).not.toHaveBeenCalled();
  });
});

describe('summarizeLine', () => {
  it('numbers moves from a black-to-move start position', () => {
    const pgn = '[FEN "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"]\n\n1... c5 2. Nf3 *';
    expect(summarizeLine(pgn)).toEqual({ line: '1... c5 2. Nf3', plies: 2 });
  });

  it('ignores side variations and truncates long lines', () => {
    const pgn = '1. e4 (1. d4 d5) e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 *';
    expect(summarizeLine(pgn)).toEqual({ line: '1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 …', plies: 11 });
  });

  it('returns an empty summary for unparsable PGN', () => {
    expect(summarizeLine('not a pgn 1. Zz9')).toEqual({ line: '', plies: 0 });
  });
});

describe('formatEdited', () => {
  const now = new Date(2026, 9, 16, 12);
  it('uses relative days within a week', () => {
    expect(formatEdited(new Date(2026, 9, 16, 8).toISOString(), 'en', now)).toBe('today');
    expect(formatEdited(new Date(2026, 9, 15, 23).toISOString(), 'en', now)).toBe('yesterday');
  });
  it('falls back to a short date', () => {
    expect(formatEdited(new Date(2026, 8, 1).toISOString(), 'en', now)).toBe('Sep 1');
  });
});
