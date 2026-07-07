/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDarkMode } from '../useDarkMode';

function mockMatchMedia(prefersDark: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query === '(prefers-color-scheme: dark)' ? prefersDark : false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
    onchange: null,
  }));
}

describe('useDarkMode', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.classList.remove('dark');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('defaults to light theme even when the OS prefers dark', () => {
    mockMatchMedia(true); // device is in system dark mode
    const { result } = renderHook(() => useDarkMode());

    expect(result.current.theme).toBe('light');
    expect(result.current.isDark).toBe(false);
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });

  it('respects an explicitly stored dark preference', () => {
    mockMatchMedia(false);
    window.localStorage.setItem('theme', JSON.stringify('dark'));
    const { result } = renderHook(() => useDarkMode());

    expect(result.current.theme).toBe('dark');
    expect(result.current.isDark).toBe(true);
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });

  it('respects an explicitly stored system preference on a dark device', () => {
    mockMatchMedia(true);
    window.localStorage.setItem('theme', JSON.stringify('system'));
    const { result } = renderHook(() => useDarkMode());

    expect(result.current.theme).toBe('system');
    expect(result.current.isDark).toBe(true);
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });

  it('toggle cycles light -> dark -> system -> light', () => {
    mockMatchMedia(false);
    const { result } = renderHook(() => useDarkMode());

    expect(result.current.theme).toBe('light');
    act(() => result.current.toggle());
    expect(result.current.theme).toBe('dark');
    act(() => result.current.toggle());
    expect(result.current.theme).toBe('system');
    act(() => result.current.toggle());
    expect(result.current.theme).toBe('light');
  });
});
