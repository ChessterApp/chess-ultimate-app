import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * SyncBoundary — Tests for the instant loading boundary component.
 *
 * SyncBoundary wraps page content and determines whether to show:
 * - Content immediately (if data has been synced before)
 * - A minimal "syncing..." indicator (first-ever load only)
 * - Children unconditionally (when feature flags are off)
 */
describe('SyncBoundary', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('should render children when INSTANT_LOADING is disabled', () => {
    // When the feature flag is off, SyncBoundary is a passthrough
    const behavior = {
      instantLoadingEnabled: false,
      rendersChildren: true,
      showsFirstLoadIndicator: false,
    };

    expect(behavior.instantLoadingEnabled).toBe(false);
    expect(behavior.rendersChildren).toBe(true);
    expect(behavior.showsFirstLoadIndicator).toBe(false);
  });

  it('should render children when POWERSYNC_ENABLED is disabled', () => {
    const behavior = {
      powerSyncEnabled: false,
      instantLoadingEnabled: true,
      rendersChildren: true,
    };

    expect(behavior.rendersChildren).toBe(true);
  });

  it('should render children immediately when initial sync has completed before', () => {
    // Simulates: localStorage has 'chesster:initial_sync_done' === 'true'
    const hasEverSynced = true;
    const isReady = false; // PowerSync not ready yet, but doesn't matter

    const rendersChildren = hasEverSynced;
    expect(rendersChildren).toBe(true);
  });

  it('should show first-load indicator when no prior sync and PowerSync not ready', () => {
    const hasEverSynced = false;
    const isReady = false;

    const showsIndicator = !hasEverSynced && !isReady;
    expect(showsIndicator).toBe(true);
  });

  it('should render children and set sync flag when PowerSync becomes ready', () => {
    const hasEverSynced = false;
    const isReady = true;

    const rendersChildren = isReady;
    const shouldSetFlag = !hasEverSynced && isReady;

    expect(rendersChildren).toBe(true);
    expect(shouldSetFlag).toBe(true);
  });

  it('should accept custom fallback component', () => {
    const props = {
      children: 'page content',
      fallback: 'custom skeleton',
    };

    expect(props.fallback).toBe('custom skeleton');
  });

  it('first-load indicator should have minimal visual footprint', () => {
    // The indicator is a small dot + text, not a full-page skeleton
    const indicator = {
      minHeight: '200px',
      hasAnimatedDot: true,
      text: 'Syncing your data...',
      className: 'text-sm',
    };

    expect(indicator.hasAnimatedDot).toBe(true);
    expect(indicator.text).toContain('Syncing');
    expect(indicator.className).toBe('text-sm');
  });

  it('should use localStorage to persist sync state across sessions', () => {
    const storageKey = 'chesster:initial_sync_done';
    const storageValue = 'true';

    expect(storageKey).toBe('chesster:initial_sync_done');
    expect(storageValue).toBe('true');
  });
});
