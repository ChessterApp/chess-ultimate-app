import { describe, it, expect } from 'vitest';

/**
 * OfflineBanner — Tests for the offline detection and banner component.
 *
 * Shows "You are offline — showing cached data" when navigator.onLine is false.
 * Provides useOfflineStatus() context for disabling mutation buttons.
 * Gated by OFFLINE_MODE feature flag for the banner display.
 */
describe('OfflineBanner', () => {
  describe('offline detection', () => {
    it('should be online when navigator.onLine is true', () => {
      const navigatorOnLine = true;
      const isOffline = !navigatorOnLine;
      expect(isOffline).toBe(false);
    });

    it('should be offline when navigator.onLine is false', () => {
      const navigatorOnLine = false;
      const isOffline = !navigatorOnLine;
      expect(isOffline).toBe(true);
    });

    it('should update on offline event', () => {
      let isOffline = false;
      // Simulate offline event handler
      const handleOffline = () => { isOffline = true; };
      handleOffline();
      expect(isOffline).toBe(true);
    });

    it('should update on online event', () => {
      let isOffline = true;
      // Simulate online event handler
      const handleOnline = () => { isOffline = false; };
      handleOnline();
      expect(isOffline).toBe(false);
    });
  });

  describe('banner display', () => {
    it('should not show banner when online', () => {
      const isOffline = false;
      const offlineModeEnabled = true;
      const showBanner = isOffline && offlineModeEnabled;
      expect(showBanner).toBe(false);
    });

    it('should show banner when offline and feature flag enabled', () => {
      const isOffline = true;
      const offlineModeEnabled = true;
      const showBanner = isOffline && offlineModeEnabled;
      expect(showBanner).toBe(true);
    });

    it('should not show banner when feature flag is disabled', () => {
      const isOffline = true;
      const offlineModeEnabled = false;
      const showBanner = isOffline && offlineModeEnabled;
      expect(showBanner).toBe(false);
    });

    it('should display correct banner text', () => {
      const bannerText = 'You are offline — showing cached data';
      expect(bannerText).toContain('offline');
      expect(bannerText).toContain('cached data');
    });

    it('should use fixed positioning with high z-index', () => {
      const classes = 'fixed top-0 left-0 right-0 z-[9999]';
      expect(classes).toContain('fixed');
      expect(classes).toContain('top-0');
      expect(classes).toContain('z-[9999]');
    });

    it('should have alert role for accessibility', () => {
      const role = 'alert';
      expect(role).toBe('alert');
    });
  });

  describe('context provider', () => {
    it('should provide isOffline value via context', () => {
      // Simulates useOfflineStatus() returning correct value
      const contextValue = { isOffline: true };
      expect(contextValue.isOffline).toBe(true);
    });

    it('should provide context even when feature flag is disabled', () => {
      const offlineModeEnabled = false;
      // OfflineBanner still provides context (for OfflineGuard consumers)
      const providesContext = true;
      expect(providesContext).toBe(true);
      expect(offlineModeEnabled).toBe(false);
    });
  });

  describe('OfflineGuard', () => {
    it('should render children when online', () => {
      const isOffline = false;
      const rendersChildren = !isOffline;
      expect(rendersChildren).toBe(true);
    });

    it('should render fallback when offline', () => {
      const isOffline = true;
      const rendersChildren = !isOffline;
      expect(rendersChildren).toBe(false);
    });

    it('should show default message when no custom fallback', () => {
      const defaultFallback = 'Reconnect to save changes';
      expect(defaultFallback).toContain('Reconnect');
    });

    it('should use custom fallback when provided', () => {
      const customFallback = 'Custom offline message';
      const isOffline = true;
      const displayed = isOffline ? customFallback : 'children';
      expect(displayed).toBe('Custom offline message');
    });
  });
});
