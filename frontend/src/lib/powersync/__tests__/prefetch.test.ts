import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  trackPageVisit,
  setLastPage,
  getUsageRanking,
  buildPrefetchQueue,
  processPrefetchQueue,
  type PrefetchTask,
} from '../prefetch';

describe('prefetch queue', () => {
  let storage: Record<string, string>;

  beforeEach(() => {
    storage = {};
    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => storage[key] ?? null),
      setItem: vi.fn((key: string, value: string) => {
        storage[key] = value;
      }),
      removeItem: vi.fn((key: string) => {
        delete storage[key];
      }),
    });
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(''))));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('trackPageVisit', () => {
    it('records a new page visit', () => {
      trackPageVisit('/dashboard');
      const saved = JSON.parse(storage['chesster:pageUsage']);
      expect(saved['/dashboard']).toBe(1);
    });

    it('increments existing page count', () => {
      storage['chesster:pageUsage'] = JSON.stringify({ '/dashboard': 3 });
      trackPageVisit('/dashboard');
      const saved = JSON.parse(storage['chesster:pageUsage']);
      expect(saved['/dashboard']).toBe(4);
    });

    it('tracks multiple pages independently', () => {
      trackPageVisit('/dashboard');
      trackPageVisit('/puzzle');
      trackPageVisit('/dashboard');
      const saved = JSON.parse(storage['chesster:pageUsage']);
      expect(saved['/dashboard']).toBe(2);
      expect(saved['/puzzle']).toBe(1);
    });
  });

  describe('setLastPage', () => {
    it('saves the last visited page', () => {
      setLastPage('/analysis');
      expect(storage['chesster:lastPage']).toBe('/analysis');
    });
  });

  describe('getUsageRanking', () => {
    it('returns empty array when no usage data', () => {
      expect(getUsageRanking()).toEqual([]);
    });

    it('returns pages sorted by visit count descending', () => {
      storage['chesster:pageUsage'] = JSON.stringify({
        '/puzzle': 5,
        '/dashboard': 20,
        '/database': 10,
      });
      expect(getUsageRanking()).toEqual(['/dashboard', '/database', '/puzzle']);
    });
  });

  describe('buildPrefetchQueue', () => {
    it('always includes subscription status at priority 0', () => {
      const queue = buildPrefetchQueue();
      const subTask = queue.find((t) => t.url === '/api/subscription/status');
      expect(subTask).toBeDefined();
      expect(subTask!.priority).toBe(0);
    });

    it('includes last page data at priority 1', () => {
      storage['chesster:lastPage'] = '/database';
      const queue = buildPrefetchQueue();
      const dbTask = queue.find(
        (t) =>
          t.url.includes('/api/openings/games/by-position') && t.priority === 1
      );
      expect(dbTask).toBeDefined();
    });

    it('includes dashboard data at priority 2', () => {
      const queue = buildPrefetchQueue();
      const dashTask = queue.find(
        (t) => t.url === '/api/games' && t.priority === 2
      );
      expect(dashTask).toBeDefined();
    });

    it('includes usage-ranked pages at priority 3+', () => {
      storage['chesster:pageUsage'] = JSON.stringify({
        '/puzzle': 10,
        '/courses': 5,
      });
      const queue = buildPrefetchQueue();
      const puzzleTask = queue.find(
        (t) => t.url === '/api/puzzles' && t.priority >= 3
      );
      expect(puzzleTask).toBeDefined();
    });

    it('includes global catalog at priority 100', () => {
      const queue = buildPrefetchQueue();
      const globalTasks = queue.filter((t) => t.priority === 100);
      expect(globalTasks.length).toBeGreaterThan(0);
    });

    it('is sorted by priority ascending', () => {
      storage['chesster:lastPage'] = '/dashboard';
      storage['chesster:pageUsage'] = JSON.stringify({
        '/puzzle': 10,
        '/courses': 5,
      });
      const queue = buildPrefetchQueue();
      for (let i = 1; i < queue.length; i++) {
        expect(queue[i].priority).toBeGreaterThanOrEqual(queue[i - 1].priority);
      }
    });

    it('deduplicates URLs across priorities', () => {
      // /api/subscription/status is in both priority 0 and dashboard (priority 2)
      storage['chesster:lastPage'] = '/dashboard';
      const queue = buildPrefetchQueue();
      const subTasks = queue.filter(
        (t) => t.url === '/api/subscription/status'
      );
      expect(subTasks).toHaveLength(1);
      expect(subTasks[0].priority).toBe(0); // keeps lowest priority
    });
  });

  describe('processPrefetchQueue', () => {
    it('fetches each URL in order', async () => {
      const tasks: PrefetchTask[] = [
        { url: '/api/subscription/status', priority: 0 },
        { url: '/api/games', priority: 2 },
      ];
      await processPrefetchQueue(tasks);
      expect(fetch).toHaveBeenCalledTimes(2);
      expect(fetch).toHaveBeenNthCalledWith(
        1,
        '/api/subscription/status',
        expect.any(Object)
      );
      expect(fetch).toHaveBeenNthCalledWith(
        2,
        '/api/games',
        expect.any(Object)
      );
    });

    it('continues processing when a fetch fails', async () => {
      vi.mocked(fetch)
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValueOnce(new Response(''));
      const tasks: PrefetchTask[] = [
        { url: '/api/fail', priority: 0 },
        { url: '/api/succeed', priority: 1 },
      ];
      await processPrefetchQueue(tasks);
      expect(fetch).toHaveBeenCalledTimes(2);
    });

    it('does nothing for empty queue', async () => {
      await processPrefetchQueue([]);
      expect(fetch).not.toHaveBeenCalled();
    });
  });
});
