'use client';

import { useEffect } from 'react';

/**
 * Client component that runs localStorage migrations on mount
 * This fixes stale cached values that users have from previous versions
 */
export default function LocalStorageMigration() {
  useEffect(() => {
    // Migration: Reset stale animation duration values
    // Old default was 300ms, new default is 50ms
    // Users who visited before the change still have 300ms cached
    try {
      const animDuration = localStorage.getItem('board_ui_animation_duration');
      if (animDuration) {
        const value = parseInt(animDuration, 10);
        // If value is > 100ms, it's stale from old default (300ms)
        // Remove it so the new default (50ms) takes effect
        if (!isNaN(value) && value > 100) {
          localStorage.removeItem('board_ui_animation_duration');
          console.log('[Migration] Removed stale animation duration:', value);
        }
      }
    } catch (err) {
      // Ignore errors in SSR or if localStorage is unavailable
      console.error('[Migration] Failed to migrate animation duration:', err);
    }
  }, []);

  return null;
}
