/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, afterEach } from 'vitest';
import { renderHook, waitFor, cleanup } from '@testing-library/react';
import { BOARD_THEMES } from '../helper';
import { resolveBoardTheme, useBoardTheme, BOARD_THEME_STORAGE_KEY } from '../useBoardTheme';

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe('resolveBoardTheme', () => {
  it('maps a known key to its colours', () => {
    expect(resolveBoardTheme('wood')).toBe(BOARD_THEMES.wood);
  });

  it('falls back to the default (chessbase) for missing/invalid keys', () => {
    expect(resolveBoardTheme(undefined)).toBe(BOARD_THEMES.chessbase);
    expect(resolveBoardTheme('nope')).toBe(BOARD_THEMES.chessbase);
    expect(resolveBoardTheme(42)).toBe(BOARD_THEMES.chessbase);
  });
});

describe('useBoardTheme', () => {
  it('returns the theme stored by the settings page', async () => {
    // usehooks-ts stores JSON, like the settings page's useLocalStorage.
    localStorage.setItem(BOARD_THEME_STORAGE_KEY, JSON.stringify('green'));
    const { result } = renderHook(() => useBoardTheme());
    await waitFor(() => expect(result.current).toBe(BOARD_THEMES.green));
    expect(result.current.lightSquareColor).toBe(BOARD_THEMES.green.lightSquareColor);
  });

  it('returns the default when nothing is stored', () => {
    const { result } = renderHook(() => useBoardTheme());
    expect(result.current).toBe(BOARD_THEMES.chessbase);
  });

  it('returns the default for an invalid stored value', async () => {
    localStorage.setItem(BOARD_THEME_STORAGE_KEY, JSON.stringify('rainbow'));
    const { result } = renderHook(() => useBoardTheme());
    await waitFor(() => expect(result.current).toBe(BOARD_THEMES.chessbase));
  });
});
