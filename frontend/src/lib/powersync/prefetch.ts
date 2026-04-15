/**
 * Prioritized Prefetch Queue — Whop-style prefetch on app launch.
 *
 * On app launch, prefetches data in priority order:
 *  0. Subscription status (gates UI)
 *  1. Last visited page data (from localStorage)
 *  2. Dashboard data (most common landing)
 *  3+. Usage-ranked pages (from localStorage tracking)
 *  100. Global catalog data (courses, puzzles)
 *
 * Prefetch fires fetch requests so the Service Worker caches them.
 * The queue processes sequentially to avoid flooding the network.
 */

const USAGE_KEY = 'chesster:pageUsage';
const LAST_PAGE_KEY = 'chesster:lastPage';

export interface PrefetchTask {
  url: string;
  priority: number;
}

// Map page paths to prefetch URLs
const PAGE_PREFETCH_MAP: Record<string, string[]> = {
  '/dashboard': ['/api/subscription/status', '/api/games'],
  '/database': ['/api/openings/games/by-position?fen=rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR%20w%20KQkq%20-%200%201'],
  '/puzzle': ['/api/puzzles'],
  '/courses': ['/api/courses'],
  '/analysis': [],
};

/**
 * Record a page visit for usage tracking.
 */
export function trackPageVisit(path: string): void {
  try {
    const raw = localStorage.getItem(USAGE_KEY);
    const usage: Record<string, number> = raw ? JSON.parse(raw) : {};
    usage[path] = (usage[path] || 0) + 1;
    localStorage.setItem(USAGE_KEY, JSON.stringify(usage));
  } catch {
    // localStorage unavailable — ignore
  }
}

/**
 * Record the last visited page.
 */
export function setLastPage(path: string): void {
  try {
    localStorage.setItem(LAST_PAGE_KEY, path);
  } catch {
    // localStorage unavailable — ignore
  }
}

/**
 * Get usage ranking sorted by visit count descending.
 */
export function getUsageRanking(): string[] {
  try {
    const raw = localStorage.getItem(USAGE_KEY);
    if (!raw) return [];
    const usage: Record<string, number> = JSON.parse(raw);
    return Object.entries(usage)
      .sort(([, a], [, b]) => b - a)
      .map(([path]) => path);
  } catch {
    return [];
  }
}

/**
 * Build the prioritized prefetch task list.
 */
export function buildPrefetchQueue(): PrefetchTask[] {
  const tasks: PrefetchTask[] = [];
  const seen = new Set<string>();

  function addTasks(urls: string[], priority: number) {
    for (const url of urls) {
      if (!seen.has(url)) {
        seen.add(url);
        tasks.push({ url, priority });
      }
    }
  }

  // Priority 0: Subscription status
  addTasks(['/api/subscription/status'], 0);

  // Priority 1: Last visited page data
  try {
    const lastPage = localStorage.getItem(LAST_PAGE_KEY);
    if (lastPage && PAGE_PREFETCH_MAP[lastPage]) {
      addTasks(PAGE_PREFETCH_MAP[lastPage], 1);
    }
  } catch {
    // ignore
  }

  // Priority 2: Dashboard data
  addTasks(PAGE_PREFETCH_MAP['/dashboard'] || [], 2);

  // Priority 3+: Usage-ranked pages
  const ranked = getUsageRanking();
  ranked.forEach((page, i) => {
    const urls = PAGE_PREFETCH_MAP[page];
    if (urls) {
      addTasks(urls, 3 + i);
    }
  });

  // Priority 100: Global catalog
  addTasks(['/api/courses', '/api/puzzles'], 100);

  // Sort by priority
  tasks.sort((a, b) => a.priority - b.priority);

  return tasks;
}

/**
 * Process the prefetch queue sequentially.
 * Each fetch populates the Service Worker cache.
 * Errors are silently ignored — prefetch is best-effort.
 */
export async function processPrefetchQueue(tasks: PrefetchTask[]): Promise<void> {
  for (const task of tasks) {
    try {
      await fetch(task.url, { priority: 'low' } as RequestInit);
    } catch {
      // Prefetch is best-effort — skip failures
    }
  }
}

/**
 * Run the full prefetch on app launch.
 */
export async function runPrefetch(): Promise<void> {
  // Wait a tick so the main thread finishes rendering first
  await new Promise((resolve) => setTimeout(resolve, 100));
  const queue = buildPrefetchQueue();
  await processPrefetchQueue(queue);
}
