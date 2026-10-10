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
    shareDatabase: vi.fn(),
    revokeShare: vi.fn(),
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
  h.fns.shareDatabase.mockResolvedValue('sdb-token-xyz');
  h.fns.revokeShare.mockResolvedValue(true);
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

  it('shows the 📖 icon on Master and the folder icon only on the default db pill', async () => {
    const { container } = render(
      <DatabasePillRow masterGameCount={100} selectedDatabaseId={null} onSelect={vi.fn()} />,
    );
    await waitFor(() => expect(h.fns.listDeleted).toHaveBeenCalled());

    // Master pill carries the 📖 emoji (migrated from the old "📖 Database" chip).
    expect(screen.getByText('📖')).toBeTruthy();

    // The folder icon renders on the default "My Games" pill...
    const defaultPill = screen.getByText('My Games').closest('[role="button"]');
    expect(defaultPill?.querySelector('[data-testid="FolderOpenIcon"]')).toBeTruthy();

    // ...but not on a non-default custom db pill.
    const customPill = screen.getByText('Openings').closest('[role="button"]');
    expect(customPill?.querySelector('[data-testid="FolderOpenIcon"]')).toBeNull();

    // And exactly one folder icon exists across the whole row.
    expect(container.querySelectorAll('[data-testid="FolderOpenIcon"]')).toHaveLength(1);
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

  it('hides the share affordance for the default db but shows it for user dbs', () => {
    render(<DatabasePillRow masterGameCount={100} selectedDatabaseId={null} onSelect={vi.fn()} />);
    expect(screen.queryByLabelText('Share My Games')).toBeNull();
    expect(screen.getByLabelText('Share Openings')).toBeTruthy();
  });

  it('mints a share link and shows the /database?sdb= URL on click', async () => {
    render(<DatabasePillRow masterGameCount={100} selectedDatabaseId={null} onSelect={vi.fn()} />);

    fireEvent.click(screen.getByLabelText('Share Openings'));
    await waitFor(() => expect(h.fns.shareDatabase).toHaveBeenCalledWith('db-openings'));

    const field = await screen.findByDisplayValue(/\/database\?sdb=sdb-token-xyz$/);
    expect(field).toBeTruthy();
  });

  it('reuses an already-minted token without re-calling the server', async () => {
    h.state = {
      databases: [DEFAULT_DB, { ...OPENINGS_DB, share_token: 'existing-token' }],
      error: null,
      ...h.fns,
    };
    render(<DatabasePillRow masterGameCount={100} selectedDatabaseId={null} onSelect={vi.fn()} />);

    fireEvent.click(screen.getByLabelText('Share Openings'));
    expect(await screen.findByDisplayValue(/sdb=existing-token$/)).toBeTruthy();
    expect(h.fns.shareDatabase).not.toHaveBeenCalled();
  });

  it('revokes a shared link from the popover', async () => {
    h.state = {
      databases: [DEFAULT_DB, { ...OPENINGS_DB, share_token: 'existing-token' }],
      error: null,
      ...h.fns,
    };
    render(<DatabasePillRow masterGameCount={100} selectedDatabaseId={null} onSelect={vi.fn()} />);

    fireEvent.click(screen.getByLabelText('Share Openings'));
    fireEvent.click(await screen.findByText('Revoke'));
    await waitFor(() => expect(h.fns.revokeShare).toHaveBeenCalledWith('db-openings'));
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
