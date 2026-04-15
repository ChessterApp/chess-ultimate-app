// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import React from 'react';

// Track current mock value for OFFLINE_MODE
let mockOfflineMode = true;

vi.mock('@/lib/feature-flags', () => ({
  get OFFLINE_MODE() { return mockOfflineMode; },
}));

import OfflineBanner, { useOfflineStatus, OfflineGuard } from '../OfflineBanner';

function OfflineStatusReader() {
  const { isOffline } = useOfflineStatus();
  return <span data-testid="offline-status">{isOffline ? 'offline' : 'online'}</span>;
}

describe('OfflineBanner component', () => {
  let originalOnLine: boolean;

  beforeEach(() => {
    originalOnLine = navigator.onLine;
    Object.defineProperty(navigator, 'onLine', { value: true, writable: true, configurable: true });
    mockOfflineMode = true;
  });

  afterEach(() => {
    Object.defineProperty(navigator, 'onLine', { value: originalOnLine, writable: true, configurable: true });
    vi.restoreAllMocks();
  });

  it('does not show banner when online', () => {
    render(<OfflineBanner><div>child</div></OfflineBanner>);
    expect(screen.queryByTestId('offline-banner')).toBeNull();
    expect(screen.getByText('child')).toBeDefined();
  });

  it('shows banner when offline', () => {
    Object.defineProperty(navigator, 'onLine', { value: false, writable: true, configurable: true });
    render(<OfflineBanner><div>child</div></OfflineBanner>);
    expect(screen.getByTestId('offline-banner')).toBeDefined();
    expect(screen.getByText('You are offline — showing cached data')).toBeDefined();
  });

  it('banner has alert role for accessibility', () => {
    Object.defineProperty(navigator, 'onLine', { value: false, writable: true, configurable: true });
    render(<OfflineBanner />);
    const banner = screen.getByTestId('offline-banner');
    expect(banner.getAttribute('role')).toBe('alert');
  });

  it('responds to offline event', () => {
    render(<OfflineBanner><div>child</div></OfflineBanner>);
    expect(screen.queryByTestId('offline-banner')).toBeNull();

    act(() => {
      Object.defineProperty(navigator, 'onLine', { value: false, writable: true, configurable: true });
      window.dispatchEvent(new Event('offline'));
    });

    expect(screen.getByTestId('offline-banner')).toBeDefined();
  });

  it('responds to online event after being offline', () => {
    Object.defineProperty(navigator, 'onLine', { value: false, writable: true, configurable: true });
    render(<OfflineBanner><div>child</div></OfflineBanner>);
    expect(screen.getByTestId('offline-banner')).toBeDefined();

    act(() => {
      Object.defineProperty(navigator, 'onLine', { value: true, writable: true, configurable: true });
      window.dispatchEvent(new Event('online'));
    });

    expect(screen.queryByTestId('offline-banner')).toBeNull();
  });

  it('does not show banner when feature flag is disabled', () => {
    mockOfflineMode = false;
    Object.defineProperty(navigator, 'onLine', { value: false, writable: true, configurable: true });
    render(<OfflineBanner><div>child</div></OfflineBanner>);
    expect(screen.queryByTestId('offline-banner')).toBeNull();
    // Children still rendered
    expect(screen.getByText('child')).toBeDefined();
  });

  it('still provides context when feature flag is disabled', () => {
    mockOfflineMode = false;
    Object.defineProperty(navigator, 'onLine', { value: false, writable: true, configurable: true });
    render(
      <OfflineBanner>
        <OfflineStatusReader />
      </OfflineBanner>
    );
    expect(screen.getByTestId('offline-status').textContent).toBe('offline');
  });
});

describe('useOfflineStatus context', () => {
  let originalOnLine: boolean;

  beforeEach(() => {
    originalOnLine = navigator.onLine;
    mockOfflineMode = true;
  });

  afterEach(() => {
    Object.defineProperty(navigator, 'onLine', { value: originalOnLine, writable: true, configurable: true });
  });

  it('provides isOffline=false when online', () => {
    Object.defineProperty(navigator, 'onLine', { value: true, writable: true, configurable: true });
    render(
      <OfflineBanner>
        <OfflineStatusReader />
      </OfflineBanner>
    );
    expect(screen.getByTestId('offline-status').textContent).toBe('online');
  });

  it('provides isOffline=true when offline', () => {
    Object.defineProperty(navigator, 'onLine', { value: false, writable: true, configurable: true });
    render(
      <OfflineBanner>
        <OfflineStatusReader />
      </OfflineBanner>
    );
    expect(screen.getByTestId('offline-status').textContent).toBe('offline');
  });
});

describe('OfflineGuard component', () => {
  let originalOnLine: boolean;

  beforeEach(() => {
    originalOnLine = navigator.onLine;
    mockOfflineMode = true;
  });

  afterEach(() => {
    Object.defineProperty(navigator, 'onLine', { value: originalOnLine, writable: true, configurable: true });
  });

  it('renders children when online', () => {
    Object.defineProperty(navigator, 'onLine', { value: true, writable: true, configurable: true });
    render(
      <OfflineBanner>
        <OfflineGuard>
          <button>Save</button>
        </OfflineGuard>
      </OfflineBanner>
    );
    expect(screen.getByText('Save')).toBeDefined();
    expect(screen.queryByTestId('offline-guard')).toBeNull();
  });

  it('shows default fallback when offline', () => {
    Object.defineProperty(navigator, 'onLine', { value: false, writable: true, configurable: true });
    render(
      <OfflineBanner>
        <OfflineGuard>
          <button>Save</button>
        </OfflineGuard>
      </OfflineBanner>
    );
    expect(screen.queryByText('Save')).toBeNull();
    expect(screen.getByTestId('offline-guard')).toBeDefined();
    expect(screen.getByText('Reconnect to save changes')).toBeDefined();
  });

  it('shows custom fallback when offline', () => {
    Object.defineProperty(navigator, 'onLine', { value: false, writable: true, configurable: true });
    render(
      <OfflineBanner>
        <OfflineGuard fallback={<span>Custom offline</span>}>
          <button>Save</button>
        </OfflineGuard>
      </OfflineBanner>
    );
    expect(screen.queryByText('Save')).toBeNull();
    expect(screen.getByText('Custom offline')).toBeDefined();
  });
});
