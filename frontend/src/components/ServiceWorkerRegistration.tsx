'use client';
import { useEffect } from 'react';

export default function ServiceWorkerRegistration() {
  useEffect(() => {
    if ('serviceWorker' in navigator) {
      const v = process.env.NEXT_PUBLIC_ASSET_VERSION || '1';
      navigator.serviceWorker.register('/sw.js?v=' + v).catch(() => {});
    }
  }, []);
  return null;
}
