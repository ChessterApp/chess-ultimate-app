// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

// next-intl: return the key so assertions are locale-independent
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

// apiFetch is called on mount for the master DB game count — stub it out
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(() => new Promise(() => {})),
}));

// GameTable renders the games list — stub with a marker per game
vi.mock('../GameTable', () => ({
  default: ({ games }: { games: any[] }) => (
    <div data-testid="game-table">{games.length} games</div>
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

import MasterGamesPanel from '../MasterGamesPanel';

const FEN_AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1';

const games = [
  { id: 1, white_player: 'Carlsen', black_player: 'Caruana', result: '1-0' },
  { id: 2, white_player: 'Nakamura', black_player: 'Firouzja', result: '1/2-1/2' },
] as any[];

describe('MasterGamesPanel (board position driven)', () => {
  it('renders the master games for the given position', () => {
    render(<MasterGamesPanel fen={FEN_AFTER_E4} masterGames={games} masterGamesTotal={12345} />);

    expect(screen.getByTestId('game-table').textContent).toBe('2 games');
    expect(screen.getByText('12,345 games reach this position')).toBeTruthy();
  });

  it('has no repertoire game-linking UI', () => {
    render(<MasterGamesPanel fen={FEN_AFTER_E4} masterGames={games} masterGamesTotal={12345} />);

    expect(screen.queryByText(/viewAllGames/)).toBeNull();
    expect(screen.queryByText(/Linked Games/)).toBeNull();
  });

  it('renders empty state (not a crash) when no games are found', () => {
    render(<MasterGamesPanel fen={FEN_AFTER_E4} masterGames={[]} masterGamesTotal={0} />);

    expect(screen.getByTestId('empty-state').textContent).toContain('noMasterGames');
  });
});
