// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// Mock the data hook so the pill row renders against controlled state. The hook
// is exercised directly in src/hooks/__tests__/useDatabases.test.ts.
const h = vi.hoisted(() => ({
  fns: {
    refresh: vi.fn(),
    createDatabase: vi.fn(),
    renameDatabase: vi.fn(),
    deleteDatabase: vi.fn(),
    restoreDatabase: vi.fn(),
    listDeleted: vi.fn(),
  },
  state: {} as Record<string, unknown>,
}));

vi.mock('@/hooks/useDatabases', () => ({
  useDatabases: () => h.state,
}));

import DatabasePillRow from '../DatabasePillRow';

const DEFAULT_DB = { id: 'db-default', name: 'My Games', is_default: true, game_count: 5 };
const OPENINGS_DB = { id: 'db-openings', name: 'Openings', is_default: false, game_count: 2 };

beforeEach(() => {
  vi.clearAllMocks();
  h.fns.refresh.mockResolvedValue([DEFAULT_DB, OPENINGS_DB]);
  h.fns.listDeleted.mockResolvedValue([]);
  h.fns.deleteDatabase.mockResolvedValue(true);
  h.fns.restoreDatabase.mockResolvedValue({ ...OPENINGS_DB });
  h.state = { databases: [DEFAULT_DB, OPENINGS_DB], error: null, ...h.fns };
});

describe('DatabasePillRow', () => {
  it('renders Master, user db pills, and the + New affordance', async () => {
    render(<DatabasePillRow masterGameCount={100} selectedDatabaseId={null} onSelect={vi.fn()} />);
    await waitFor(() => expect(h.fns.listDeleted).toHaveBeenCalled());

    expect(screen.getByText('Master')).toBeTruthy();
    expect(screen.getByText('Openings')).toBeTruthy();
    expect(screen.getByText('New')).toBeTruthy();
    // Nothing deleted → no restore entry point.
    expect(screen.queryByText('Recently deleted')).toBeNull();
  });

  it('renders cleanly with only the default db (empty user-db state)', async () => {
    h.state = { databases: [DEFAULT_DB], error: null, ...h.fns };
    render(<DatabasePillRow masterGameCount={0} selectedDatabaseId={null} onSelect={vi.fn()} />);
    await waitFor(() => expect(h.fns.listDeleted).toHaveBeenCalled());

    expect(screen.getByText('Master')).toBeTruthy();
    expect(screen.getByText('New')).toBeTruthy();
  });

  it('hides the delete affordance for the default db but shows it for user dbs', () => {
    render(<DatabasePillRow masterGameCount={100} selectedDatabaseId={null} onSelect={vi.fn()} />);
    expect(screen.queryByLabelText('Delete My Games')).toBeNull();
    expect(screen.getByLabelText('Delete Openings')).toBeTruthy();
  });

  it('confirms before deleting and switches to the default when the active db is removed', async () => {
    const onSelect = vi.fn();
    render(<DatabasePillRow masterGameCount={100} selectedDatabaseId="db-openings" onSelect={onSelect} />);

    fireEvent.click(screen.getByLabelText('Delete Openings'));
    expect(
      screen.getByText("Delete 'Openings'? Its 2 games will be recoverable for 30 days."),
    ).toBeTruthy();

    fireEvent.click(screen.getByText('Delete'));
    await waitFor(() => expect(h.fns.deleteDatabase).toHaveBeenCalledWith('db-openings'));
    // Active db was deleted → fall back to the default db.
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith('db-default'));
  });

  it('does not delete when the confirmation is cancelled', async () => {
    render(<DatabasePillRow masterGameCount={100} selectedDatabaseId={null} onSelect={vi.fn()} />);

    fireEvent.click(screen.getByLabelText('Delete Openings'));
    fireEvent.click(screen.getByText('Cancel'));

    expect(h.fns.deleteDatabase).not.toHaveBeenCalled();
  });

  it('shows the recently-deleted panel and restores from it', async () => {
    h.fns.listDeleted.mockResolvedValue([
      { id: 'db-openings', name: 'Openings', deleted_at: '2026-01-01T00:00:00+00:00', game_count: 2, days_left: 25 },
    ]);
    h.state = { databases: [DEFAULT_DB], error: null, ...h.fns };
    const onSelect = vi.fn();
    render(<DatabasePillRow masterGameCount={0} selectedDatabaseId={null} onSelect={onSelect} />);

    const entry = await screen.findByText('Recently deleted');
    fireEvent.click(entry);

    expect(await screen.findByText('2 games · 25 days left')).toBeTruthy();
    fireEvent.click(screen.getByText('Restore'));

    await waitFor(() => expect(h.fns.restoreDatabase).toHaveBeenCalledWith('db-openings'));
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith('db-openings'));
  });
});
