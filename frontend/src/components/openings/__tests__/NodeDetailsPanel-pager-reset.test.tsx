// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';

// next-intl: return the key so assertions are locale-independent
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

// apiFetch is called on mount for the master DB game count — stub it out
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(() => new Promise(() => {})),
}));

// GameTable renders the current page slice — expose the ids so we can assert
// which page is showing.
vi.mock('../GameTable', () => ({
  default: ({ games }: { games: any[] }) => (
    <div data-testid="game-table">{games.map((g) => g.id).join(',')}</div>
  ),
}));

vi.mock('../MasterGamesFilter', () => ({ default: () => <div data-testid="filters" /> }));
vi.mock('../LichessExplorerTab', () => ({ default: () => null }));
vi.mock('../ChessComExplorerTab', () => ({ default: () => null }));
vi.mock('../ExplorerTabs', () => ({
  default: ({ twicContent }: { twicContent: React.ReactNode }) => <div>{twicContent}</div>,
}));
vi.mock('../EmptyState', () => ({
  default: ({ message }: { message: string }) => <div data-testid="empty-state">{message}</div>,
}));

import NodeDetailsPanel from '../NodeDetailsPanel';
import type { MasterGamesFilterState } from '../MasterGamesFilter';

const FEN_AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1';

// 25 games → 3 pages at 10 per page (ids 0..24)
const makeGames = (n: number) =>
  Array.from({ length: n }, (_, i) => ({ id: i, white_player: 'W', black_player: 'B', result: '1-0' })) as any[];

const emptyFilters: MasterGamesFilterState = {
  playerName: '', opponentName: '', playerColor: '', result: '', sortBy: 'date_desc',
  whiteEloMin: 0, whiteEloMax: 3500, blackEloMin: 0, blackEloMax: 3500,
  dateFrom: '', dateTo: '', ecoCode: '', eventName: '',
};

const baseProps = {
  onUpdateNotes: vi.fn(),
  onToggleCritical: vi.fn(),
  onDeleteNode: vi.fn(),
  onSearchGames: vi.fn(),
  onMasterGamesFilterChange: vi.fn(),
  gameLinks: [],
  gameLinksLoading: false,
};

describe('NodeDetailsPanel games pager reset/clamp', () => {
  it('resets to page 0 when the filter set changes (stale-page bug)', () => {
    const { rerender } = render(
      <NodeDetailsPanel
        {...baseProps}
        node={null}
        fallbackFen={FEN_AFTER_E4}
        masterGames={makeGames(25)}
        masterGamesTotal={25}
        masterGamesFilters={emptyFilters}
      />
    );

    // Advance to the last page (page index 2 → ids 20..24). The pager renders
    // exactly two icon buttons: [prev, next].
    const next = () => screen.getAllByRole('button')[1];
    fireEvent.click(next());
    fireEvent.click(next());
    expect(screen.getByTestId('game-table').textContent).toBe('20,21,22,23,24');

    // Applying a player-name filter (new filter object, shorter result set)
    // must snap the pager back to page 0 rather than slicing off the end.
    rerender(
      <NodeDetailsPanel
        {...baseProps}
        node={null}
        fallbackFen={FEN_AFTER_E4}
        masterGames={makeGames(3)}
        masterGamesTotal={3}
        masterGamesFilters={{ ...emptyFilters, playerName: 'Carlsen' }}
      />
    );

    expect(screen.getByTestId('game-table').textContent).toBe('0,1,2');
  });

  it('clamps the current page when the result set shrinks under it', () => {
    const { rerender } = render(
      <NodeDetailsPanel
        {...baseProps}
        node={null}
        fallbackFen={FEN_AFTER_E4}
        masterGames={makeGames(25)}
        masterGamesTotal={25}
        masterGamesFilters={emptyFilters}
      />
    );

    const next = () => screen.getAllByRole('button')[1];
    fireEvent.click(next());
    fireEvent.click(next());
    expect(screen.getByTestId('game-table').textContent).toBe('20,21,22,23,24');

    // Same filter object identity, but the list shrinks to a single page —
    // the clamp effect must pull the page back so the slice is non-empty.
    rerender(
      <NodeDetailsPanel
        {...baseProps}
        node={null}
        fallbackFen={FEN_AFTER_E4}
        masterGames={makeGames(5)}
        masterGamesTotal={5}
        masterGamesFilters={emptyFilters}
      />
    );

    expect(screen.getByTestId('game-table').textContent).toBe('0,1,2,3,4');
  });
});
