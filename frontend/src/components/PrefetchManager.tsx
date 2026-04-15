'use client';
import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { PREFETCH_QUEUE } from '@/lib/feature-flags';
import { runPrefetch, trackPageVisit, setLastPage } from '@/lib/powersync/prefetch';

export default function PrefetchManager() {
  const pathname = usePathname();

  // Run prefetch queue on app launch
  useEffect(() => {
    if (!PREFETCH_QUEUE) return;
    runPrefetch().catch(() => {});
  }, []);

  // Track page visits for usage ranking
  useEffect(() => {
    if (!pathname) return;
    trackPageVisit(pathname);
    setLastPage(pathname);
  }, [pathname]);

  return null;
}
