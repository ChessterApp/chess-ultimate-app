'use client';
import { useEffect } from 'react';

export default function ServiceWorkerRegistration() {
  useEffect(() => {
    if ('serviceWorker' in navigator) {
      // v=3 cache buster forces refetch of sw.js (bypasses stale chesster-v1/v2 cache)
      navigator.serviceWorker.register('/sw.js?v=3').catch(() => {});
    }
  }, []);
  return null;
}
