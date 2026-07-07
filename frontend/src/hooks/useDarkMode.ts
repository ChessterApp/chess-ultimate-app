'use client';

import { useState, useEffect, useCallback } from 'react';
import { useLocalStorage } from 'usehooks-ts';

type Theme = 'light' | 'dark' | 'system';

function computeIsDark(t: Theme): boolean {
  if (typeof window === 'undefined') return false;
  return t === 'dark' ||
    (t === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
}

export function useDarkMode() {
  // Default to 'light' so devices with system dark mode enabled never
  // auto-activate the dark theme; dark/system are explicit opt-in via toggle.
  const [theme, setTheme] = useLocalStorage<Theme>('theme', 'light');
  const [isDark, setIsDark] = useState(() => computeIsDark(theme));

  useEffect(() => {
    const dark = computeIsDark(theme);
    document.documentElement.classList.toggle('dark', dark);
    setIsDark(dark);

    // Listen for system preference changes
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = () => {
      if (theme === 'system') {
        const sysDark = mq.matches;
        document.documentElement.classList.toggle('dark', sysDark);
        setIsDark(sysDark);
      }
    };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((prev) => {
      if (prev === 'light') return 'dark';
      if (prev === 'dark') return 'system';
      return 'light';
    });
  }, [setTheme]);

  return { theme, setTheme, toggle, isDark };
}
