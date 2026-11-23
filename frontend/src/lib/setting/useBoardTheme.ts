'use client';

import { useLocalStorage } from 'usehooks-ts';
import { BOARD_THEMES } from './helper';

export type BoardThemeKey = keyof typeof BOARD_THEMES;
export type BoardTheme = (typeof BOARD_THEMES)[BoardThemeKey];

/** Same key + default the settings page writes. */
export const BOARD_THEME_STORAGE_KEY = 'board_theme';
export const DEFAULT_BOARD_THEME: BoardThemeKey = 'chessbase';

/** Theme colours for a stored key; the default theme for a missing/unknown one. */
export function resolveBoardTheme(key: unknown): BoardTheme {
  return typeof key === 'string' && key in BOARD_THEMES
    ? BOARD_THEMES[key as BoardThemeKey]
    : BOARD_THEMES[DEFAULT_BOARD_THEME];
}

/**
 * The board colours chosen in Settings. SSR-safe: the first render uses the
 * default and the stored value is read after mount, so server and client
 * markup match. Updates live when the setting changes in another hook/tab.
 */
export function useBoardTheme(): BoardTheme {
  const [key] = useLocalStorage<string>(BOARD_THEME_STORAGE_KEY, DEFAULT_BOARD_THEME, {
    initializeWithValue: false,
  });
  return resolveBoardTheme(key);
}
