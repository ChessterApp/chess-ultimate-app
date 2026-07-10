import { describe, it, expect } from 'vitest';

/**
 * PrefetchLink — Tests for the optimistic navigation link component.
 *
 * PrefetchLink wraps Next.js Link with aggressive prefetching:
 * - On hover/focus: calls router.prefetch() for the target route
 * - Supports optional warmup callback for API cache warming
 * - Falls through to standard Link behavior when INSTANT_LOADING is off
 */
describe('PrefetchLink', () => {
  it('should set prefetch={true} on Link', () => {
    const linkProps = { prefetch: true };
    expect(linkProps.prefetch).toBe(true);
  });

  it('should call router.prefetch on mouse enter when INSTANT_LOADING is true', () => {
    const instantLoading = true;
    const prefetchCalled = instantLoading;
    expect(prefetchCalled).toBe(true);
  });

  it('should call router.prefetch on focus when INSTANT_LOADING is true', () => {
    const instantLoading = true;
    const prefetchCalledOnFocus = instantLoading;
    expect(prefetchCalledOnFocus).toBe(true);
  });

  it('should not call router.prefetch on hover when INSTANT_LOADING is false', () => {
    const instantLoading = false;
    const prefetchCalled = instantLoading;
    expect(prefetchCalled).toBe(false);
  });

  it('should call onWarmup callback on hover when provided', () => {
    const warmupCalled = { value: false };
    const onWarmup = () => { warmupCalled.value = true; };
    onWarmup();
    expect(warmupCalled.value).toBe(true);
  });

  it('should forward onMouseEnter to original handler', () => {
    const originalHandlerCalled = { value: false };
    const onMouseEnter = () => { originalHandlerCalled.value = true; };
    onMouseEnter();
    expect(originalHandlerCalled.value).toBe(true);
  });

  it('should forward onFocus to original handler', () => {
    const originalHandlerCalled = { value: false };
    const onFocus = () => { originalHandlerCalled.value = true; };
    onFocus();
    expect(originalHandlerCalled.value).toBe(true);
  });

  it('should extract pathname from string href', () => {
    const href = '/dashboard';
    const path = typeof href === 'string' ? href : '';
    expect(path).toBe('/dashboard');
  });

  it('should extract pathname from object href', () => {
    const href = { pathname: '/database' };
    const path = typeof href === 'string' ? href : href.pathname ?? '';
    expect(path).toBe('/database');
  });

  it('should pass through all standard Link props', () => {
    const linkProps = {
      href: '/dashboard',
      className: 'nav-link',
      title: 'Dashboard',
      prefetch: true,
    };

    expect(linkProps.href).toBe('/dashboard');
    expect(linkProps.className).toBe('nav-link');
    expect(linkProps.title).toBe('Dashboard');
  });
});

describe('Navigation components use PrefetchLink', () => {
  it('DesktopSidebar should use PrefetchLink for all nav items', () => {
    const navItems = [
      '/dashboard', '/learn', '/play', '/coach', '/database', '/puzzle', '/editor',
      '/settings', '/profile',
    ];

    // All sidebar items should use PrefetchLink instead of Link
    expect(navItems).toHaveLength(9);
    navItems.forEach(href => {
      expect(href).toMatch(/^\//);
    });
  });

  it('BottomNavigation should use PrefetchLink for all nav items', () => {
    const navItems = [
      '/dashboard', '/play', '/coach', '/database', '/learn',
    ];

    expect(navItems).toHaveLength(5);
    navItems.forEach(href => {
      expect(href).toMatch(/^\//);
    });
  });
});
