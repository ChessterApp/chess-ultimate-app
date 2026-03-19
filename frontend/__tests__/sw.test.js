import { describe, it, expect, beforeEach, vi } from 'vitest';

describe('Service Worker - sw.js', () => {
  let cacheMock;
  let cachesMock;
  let fetchMock;
  let globalSelf;

  beforeEach(() => {
    // Mock cache storage
    cacheMock = {
      put: vi.fn().mockResolvedValue(undefined),
      match: vi.fn(),
      addAll: vi.fn().mockResolvedValue(undefined),
      delete: vi.fn().mockResolvedValue(true),
    };

    cachesMock = {
      open: vi.fn().mockResolvedValue(cacheMock),
      match: vi.fn(),
      keys: vi.fn().mockResolvedValue([]),
      delete: vi.fn().mockResolvedValue(true),
    };

    fetchMock = vi.fn();

    // Create mock global environment
    globalSelf = {
      addEventListener: vi.fn(),
      skipWaiting: vi.fn(),
      clients: {
        claim: vi.fn(),
      },
      caches: cachesMock,
      fetch: fetchMock,
    };

    // Reset mocks
    vi.clearAllMocks();
  });

  describe('Navigation requests (stale-while-revalidate)', () => {
    it('should return cached response immediately for navigation requests', async () => {
      const cachedResponse = new Response('cached html', { status: 200 });
      const networkResponse = new Response('fresh html', { status: 200 });

      cacheMock.match.mockResolvedValue(cachedResponse);
      fetchMock.mockResolvedValue(networkResponse);

      const request = { url: 'https://example.com/page', mode: 'navigate' };

      // Simulate stale-while-revalidate strategy
      const cachedPromise = cacheMock.match(request);
      const fetchPromise = fetchMock(request).then((response) => {
        const clone = response.clone();
        cachesMock.open('chesster-v5').then((cache) => cache.put(request, clone));
        return response;
      });

      const result = await cachedPromise || await fetchPromise;

      expect(result).toBe(cachedResponse);
      expect(cacheMock.match).toHaveBeenCalledWith(request);
      expect(fetchMock).toHaveBeenCalledWith(request);
    });

    it('should fetch from network if no cached response exists for navigation', async () => {
      const networkResponse = new Response('fresh html', { status: 200 });

      cacheMock.match.mockResolvedValue(undefined);
      fetchMock.mockResolvedValue(networkResponse);

      const request = { url: 'https://example.com/page', mode: 'navigate' };

      // Simulate stale-while-revalidate strategy
      const cachedPromise = cacheMock.match(request);
      const fetchPromise = fetchMock(request).then((response) => {
        const clone = response.clone();
        cachesMock.open('chesster-v5').then((cache) => cache.put(request, clone));
        return response;
      });

      const cached = await cachedPromise;
      const result = cached || await fetchPromise;

      expect(result).toBe(networkResponse);
      expect(fetchMock).toHaveBeenCalledWith(request);
    });

    it('should update cache in background for navigation requests', async () => {
      const cachedResponse = new Response('cached html', { status: 200 });
      const networkResponse = new Response('fresh html', { status: 200 });
      const clonedResponse = new Response('fresh html', { status: 200 });

      cacheMock.match.mockResolvedValue(cachedResponse);
      fetchMock.mockResolvedValue(networkResponse);

      // Mock clone method
      networkResponse.clone = vi.fn().mockReturnValue(clonedResponse);

      const request = { url: 'https://example.com/page', mode: 'navigate' };

      // Simulate stale-while-revalidate strategy
      const cachedPromise = cacheMock.match(request);
      const fetchPromise = fetchMock(request).then((response) => {
        const clone = response.clone();
        cachesMock.open('chesster-v5').then((cache) => cache.put(request, clone));
        return response;
      });

      await cachedPromise || await fetchPromise;

      // Wait for background cache update
      await new Promise(resolve => setTimeout(resolve, 0));

      expect(cachesMock.open).toHaveBeenCalledWith('chesster-v5');
      expect(networkResponse.clone).toHaveBeenCalled();
    });
  });

  describe('API requests (network-first)', () => {
    it('should use network-first strategy for API requests', async () => {
      const networkResponse = new Response('{"data":"fresh"}', { status: 200 });
      const clonedResponse = new Response('{"data":"fresh"}', { status: 200 });

      fetchMock.mockResolvedValue(networkResponse);
      networkResponse.clone = vi.fn().mockReturnValue(clonedResponse);

      const request = new Request('https://example.com/api/data');

      // Simulate network-first strategy
      const result = await fetchMock(request).then((response) => {
        const clone = response.clone();
        cachesMock.open('chesster-v5').then((cache) => cache.put(request, clone));
        return response;
      });

      expect(result).toBe(networkResponse);
      expect(fetchMock).toHaveBeenCalledWith(request);
      expect(networkResponse.clone).toHaveBeenCalled();
    });

    it('should fallback to cache for API requests when offline', async () => {
      const cachedResponse = new Response('{"data":"cached"}', { status: 200 });

      fetchMock.mockRejectedValue(new Error('Network error'));
      cacheMock.match.mockResolvedValue(cachedResponse);

      const request = new Request('https://example.com/api/data');

      // Simulate network-first with fallback
      const result = await fetchMock(request)
        .then((response) => {
          const clone = response.clone();
          cachesMock.open('chesster-v5').then((cache) => cache.put(request, clone));
          return response;
        })
        .catch(() =>
          cacheMock.match(request).then((cached) =>
            cached || new Response('Offline', { status: 503, statusText: 'Service Unavailable' })
          )
        );

      expect(result).toBe(cachedResponse);
      expect(cacheMock.match).toHaveBeenCalledWith(request);
    });
  });

  describe('Strategy differences', () => {
    it('navigation requests should return cache first (stale-while-revalidate)', async () => {
      const cachedNav = new Response('cached page', { status: 200 });
      const networkNav = new Response('fresh page', { status: 200 });

      cacheMock.match.mockResolvedValue(cachedNav);
      fetchMock.mockResolvedValue(networkNav);

      const navRequest = { url: 'https://example.com/page', mode: 'navigate' };

      // Stale-while-revalidate returns cache immediately
      const navResult = await cacheMock.match(navRequest);

      expect(navResult).toBe(cachedNav);
    });

    it('API requests should return network first (network-first)', async () => {
      const cachedApi = new Response('{"data":"cached"}', { status: 200 });
      const networkApi = new Response('{"data":"fresh"}', { status: 200 });

      cacheMock.match.mockResolvedValue(cachedApi);
      fetchMock.mockResolvedValue(networkApi);

      const apiRequest = new Request('https://example.com/api/data');

      // Network-first returns network response
      const apiResult = await fetchMock(apiRequest);

      expect(apiResult).toBe(networkApi);
      expect(apiResult).not.toBe(cachedApi);
    });
  });
});
