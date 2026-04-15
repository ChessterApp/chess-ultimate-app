// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';

// Mock feature flags — must be before component import
vi.mock('@/lib/feature-flags', () => ({
  SYNC_INDICATOR: true,
  POWERSYNC_ENABLED: true,
  OFFLINE_MODE: true,
}));

// Mock PowerSync context
const mockDatabase = {
  currentStatus: {
    dataFlowStatus: { downloading: false, uploading: false },
  },
  registerListener: vi.fn(() => vi.fn()),
  getNextCrudTransaction: vi.fn(() => Promise.resolve(null)),
};

vi.mock('@/lib/powersync/PowerSyncProvider', () => ({
  usePowerSyncContext: () => ({
    database: mockDatabase,
    collections: null,
    isReady: true,
  }),
}));

import SyncIndicator from '../SyncIndicator';

describe('SyncIndicator component', () => {
  let originalOnLine: boolean;

  beforeEach(() => {
    vi.useFakeTimers();
    originalOnLine = navigator.onLine;
    Object.defineProperty(navigator, 'onLine', { value: true, writable: true, configurable: true });
    mockDatabase.currentStatus = {
      dataFlowStatus: { downloading: false, uploading: false },
    };
    mockDatabase.registerListener.mockReturnValue(vi.fn());
    mockDatabase.getNextCrudTransaction.mockResolvedValue(null);
  });

  afterEach(() => {
    vi.useRealTimers();
    Object.defineProperty(navigator, 'onLine', { value: originalOnLine, writable: true, configurable: true });
    vi.restoreAllMocks();
  });

  it('renders the sync indicator button', () => {
    render(<SyncIndicator />);
    expect(screen.getByTestId('sync-indicator')).toBeDefined();
  });

  it('shows synced state by default', () => {
    render(<SyncIndicator />);
    const button = screen.getByTestId('sync-indicator');
    expect(button.getAttribute('aria-label')).toBe('Sync status: Synced');
  });

  it('shows syncing state when downloading', () => {
    mockDatabase.currentStatus = {
      dataFlowStatus: { downloading: true, uploading: false },
    };
    render(<SyncIndicator />);
    const button = screen.getByTestId('sync-indicator');
    expect(button.getAttribute('aria-label')).toBe('Sync status: Syncing...');
  });

  it('shows syncing state when uploading', () => {
    mockDatabase.currentStatus = {
      dataFlowStatus: { downloading: false, uploading: true },
    };
    render(<SyncIndicator />);
    const button = screen.getByTestId('sync-indicator');
    expect(button.getAttribute('aria-label')).toBe('Sync status: Syncing...');
  });

  it('shows offline state when navigator is offline', () => {
    Object.defineProperty(navigator, 'onLine', { value: false, writable: true, configurable: true });
    render(<SyncIndicator />);
    const button = screen.getByTestId('sync-indicator');
    expect(button.getAttribute('aria-label')).toBe('Sync status: Offline');
  });

  it('toggles expanded panel on click', () => {
    render(<SyncIndicator />);
    const button = screen.getByTestId('sync-indicator');

    // Panel should not be visible initially
    expect(screen.queryByTestId('sync-panel')).toBeNull();

    // Click to expand
    fireEvent.click(button);
    expect(screen.getByTestId('sync-panel')).toBeDefined();

    // Click to collapse
    fireEvent.click(button);
    expect(screen.queryByTestId('sync-panel')).toBeNull();
  });

  it('shows last sync time as "Just now" when synced', () => {
    // When database reports synced (no downloading/uploading), lastSyncTime is set immediately
    render(<SyncIndicator />);
    fireEvent.click(screen.getByTestId('sync-indicator'));
    const panel = screen.getByTestId('sync-panel');
    expect(panel.textContent).toContain('Just now');
  });

  it('shows last sync time as "Never" when still syncing', () => {
    // When actively syncing, lastSyncTime hasn't been set yet
    mockDatabase.currentStatus = {
      dataFlowStatus: { downloading: true, uploading: false },
    };
    render(<SyncIndicator />);
    fireEvent.click(screen.getByTestId('sync-indicator'));
    const panel = screen.getByTestId('sync-panel');
    expect(panel.textContent).toContain('Never');
  });

  it('shows pending items count', async () => {
    mockDatabase.getNextCrudTransaction.mockResolvedValue({
      crud: [{ id: '1' }, { id: '2' }],
    });

    render(<SyncIndicator />);
    fireEvent.click(screen.getByTestId('sync-indicator'));

    // Wait for pending check
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });

    const panel = screen.getByTestId('sync-panel');
    expect(panel.textContent).toContain('2 items');
  });

  it('shows connection status', () => {
    render(<SyncIndicator />);
    fireEvent.click(screen.getByTestId('sync-indicator'));
    const panel = screen.getByTestId('sync-panel');
    expect(panel.textContent).toContain('Online');
  });

  it('uses registerListener for reactive status updates', () => {
    render(<SyncIndicator />);
    expect(mockDatabase.registerListener).toHaveBeenCalledWith(
      expect.objectContaining({ statusChanged: expect.any(Function) })
    );
  });

  it('responds to online/offline events', () => {
    render(<SyncIndicator />);

    // Go offline
    act(() => {
      Object.defineProperty(navigator, 'onLine', { value: false, writable: true, configurable: true });
      window.dispatchEvent(new Event('offline'));
    });

    const button = screen.getByTestId('sync-indicator');
    expect(button.getAttribute('aria-label')).toBe('Sync status: Offline');

    // Go back online
    act(() => {
      Object.defineProperty(navigator, 'onLine', { value: true, writable: true, configurable: true });
      window.dispatchEvent(new Event('online'));
    });

    expect(button.getAttribute('aria-label')).toBe('Sync status: Synced');
  });

  it('applies correct CSS classes for synced state', () => {
    render(<SyncIndicator />);
    const dot = screen.getByTestId('sync-indicator').querySelector('div');
    expect(dot?.className).toContain('bg-green-500');
    expect(dot?.className).not.toContain('animate-pulse');
  });

  it('applies correct CSS classes for syncing state', () => {
    mockDatabase.currentStatus = {
      dataFlowStatus: { downloading: true, uploading: false },
    };
    render(<SyncIndicator />);
    const dot = screen.getByTestId('sync-indicator').querySelector('div');
    expect(dot?.className).toContain('bg-green-500');
    expect(dot?.className).toContain('animate-pulse');
  });

  it('applies correct CSS classes for offline state', () => {
    Object.defineProperty(navigator, 'onLine', { value: false, writable: true, configurable: true });
    render(<SyncIndicator />);
    const dot = screen.getByTestId('sync-indicator').querySelector('div');
    expect(dot?.className).toContain('bg-gray-400');
  });
});
