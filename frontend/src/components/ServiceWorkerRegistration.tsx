'use client';
import { useEffect } from 'react';

export default function ServiceWorkerRegistration() {
  useEffect(() => {
    if ('serviceWorker' in navigator) {
      // v=4 cache buster forces refetch of sw.js (bypasses stale cache versions)
      navigator.serviceWorker.register('/sw.js?v=4').catch(() => {});
    }
  }, []);
  return null;
}
