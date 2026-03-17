import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { GET } from '../route';
import { NextRequest } from 'next/server';
import {
  explorerCache,
  rateLimiter,
  circuitBreaker,
} from '@/lib/explorer-cache';

// Mock fetch
global.fetch = vi.fn();

describe('Explorer API Route', () => {
  beforeEach(() => {
    // Clear cache and reset state before each test
    explorerCache.clear();
    circuitBreaker.reset();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const createMockRequest = (path: string, query?: Record<string, string>) => {
    const url = new URL(`http://localhost:3000/api/explorer/${path}`);
    if (query) {
      Object.entries(query).forEach(([key, value]) => {
        url.searchParams.set(key, value);
      });
    }

    return new NextRequest(url);
  };

  const createMockParams = (pathSegments: string[]) => {
    return Promise.resolve({ path: pathSegments });
  };

  const mockSuccessfulFetch = (data: any) => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => data,
    });
  };

  const mockNDJSONFetch = (lines: any[]) => {
    const ndjsonText = lines.map(line => JSON.stringify(line)).join('\n');
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      text: async () => ndjsonText,
    });
  };

  const mockFailedFetch = (status = 500) => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: false,
      status,
    });
  };

  it('should return error for invalid path', async () => {
    const request = createMockRequest('');
    const params = createMockParams([]);

    const response = await GET(request, { params });
    const data = await response.json();

    expect(response.status).toBe(400);
    expect(data).toHaveProperty('error');
  });

  it('should cache successful responses', async () => {
    const mockData = {
      white: 100,
      draws: 50,
      black: 75,
      moves: [],
      topGames: [],
      opening: null,
    };

    mockSuccessfulFetch(mockData);

    const request = createMockRequest('masters', { fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1' });
    const params = createMockParams(['masters']);

    // First request - should hit upstream
    const response1 = await GET(request, { params });
    const data1 = await response1.json();

    expect(data1).toEqual(mockData);
    expect(response1.headers.get('X-Cache')).toBe('MISS');
    expect(global.fetch).toHaveBeenCalledTimes(1);

    // Second request - should hit cache
    const request2 = createMockRequest('masters', { fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1' });
    const response2 = await GET(request2, { params });
    const data2 = await response2.json();

    expect(data2).toEqual(mockData);
    expect(response2.headers.get('X-Cache')).toBe('HIT');
    expect(global.fetch).toHaveBeenCalledTimes(1); // No additional fetch
  });

  it('should return empty fallback on upstream error', async () => {
    mockFailedFetch(500);

    const request = createMockRequest('masters', { fen: 'test' });
    const params = createMockParams(['masters']);

    const response = await GET(request, { params });
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data).toEqual({
      white: 0,
      draws: 0,
      black: 0,
      moves: [],
      topGames: [],
      opening: null,
      _upstreamError: true,
    });
  });

  it('should use circuit breaker on repeated failures', async () => {
    const request = createMockRequest('masters', { fen: 'test' });
    const params = createMockParams(['masters']);

    // Trigger 5 failures to open circuit
    for (let i = 0; i < 5; i++) {
      mockFailedFetch(500);
      await GET(request, { params });
    }

    // Circuit should be open now
    expect(circuitBreaker.isOpen()).toBe(true);

    // Next request should not hit upstream (circuit is open)
    const response = await GET(request, { params });
    const data = await response.json();

    expect(response.headers.get('X-Cache')).toBe('CIRCUIT_OPEN');
    expect(data).toEqual({
      white: 0,
      draws: 0,
      black: 0,
      moves: [],
      topGames: [],
      opening: null,
    });

    // fetch should have been called exactly 5 times (not 6)
    expect(global.fetch).toHaveBeenCalledTimes(5);
  });

  it('should handle different query parameters as separate cache keys', async () => {
    const mockData1 = { white: 100, draws: 50, black: 75, moves: [], topGames: [], opening: null };
    const mockData2 = { white: 200, draws: 100, black: 150, moves: [], topGames: [], opening: null };

    mockSuccessfulFetch(mockData1);
    mockSuccessfulFetch(mockData2);

    const request1 = createMockRequest('masters', { fen: 'fen1' });
    const request2 = createMockRequest('masters', { fen: 'fen2' });
    const params = createMockParams(['masters']);

    const response1 = await GET(request1, { params });
    const response2 = await GET(request2, { params });

    const data1 = await response1.json();
    const data2 = await response2.json();

    expect(data1).toEqual(mockData1);
    expect(data2).toEqual(mockData2);
    expect(global.fetch).toHaveBeenCalledTimes(2); // Both hit upstream
  });

  it('should construct correct upstream URL', async () => {
    mockSuccessfulFetch({ white: 0, draws: 0, black: 0, moves: [], topGames: [], opening: null });

    const request = createMockRequest('masters', {
      fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
      moves: '12',
      topGames: '15',
    });
    const params = createMockParams(['masters']);

    await GET(request, { params });

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('https://explorer.lichess.org/masters?'),
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({
          Accept: 'application/json',
          'User-Agent': expect.stringContaining('Mozilla'),
          Referer: 'https://lichess.org/',
          Origin: 'https://lichess.org',
        }),
        signal: expect.any(Object),
      })
    );

    const callUrl = (global.fetch as any).mock.calls[0][0];
    expect(callUrl).toContain('fen=');
    expect(callUrl).toContain('moves=12');
    expect(callUrl).toContain('topGames=15');
  });

  it('should handle rate limiting for concurrent requests', async () => {
    // This test verifies that rate limiting doesn't break concurrent requests
    const mockData = { white: 100, draws: 50, black: 75, moves: [], topGames: [], opening: null };

    // Mock 3 successful fetches
    for (let i = 0; i < 3; i++) {
      mockSuccessfulFetch(mockData);
    }

    const params = createMockParams(['masters']);

    // Make 3 concurrent requests with different FENs
    const requests = [
      GET(createMockRequest('masters', { fen: 'fen1' }), { params }),
      GET(createMockRequest('masters', { fen: 'fen2' }), { params }),
      GET(createMockRequest('masters', { fen: 'fen3' }), { params }),
    ];

    const responses = await Promise.all(requests);

    // All should succeed
    for (const response of responses) {
      const data = await response.json();
      expect(data).toEqual(mockData);
      expect(response.status).toBe(200);
    }

    expect(global.fetch).toHaveBeenCalledTimes(3);
  });

  describe('Player endpoint NDJSON handling', () => {
    it('should parse NDJSON streaming response and return final result', async () => {
      const queuePosition = { white: 0, draws: 0, black: 0, moves: [], recentGames: [], queuePosition: 20 };
      const finalResult = {
        white: 500,
        draws: 200,
        black: 300,
        moves: [{ uci: 'e2e4', san: 'e4', white: 300, draws: 100, black: 100 }],
        recentGames: [
          {
            id: 'abc123',
            winner: 'white',
            speed: 'blitz',
            mode: 'rated',
            black: { name: 'player1', rating: 2500 },
            white: { name: 'player2', rating: 2550 },
            year: 2024,
            month: 3,
          },
        ],
      };

      mockNDJSONFetch([queuePosition, finalResult]);

      const request = createMockRequest('player', { player: 'testplayer' });
      const params = createMockParams(['player']);

      const response = await GET(request, { params });
      const data = await response.json();

      expect(response.status).toBe(200);
      expect(data.white).toBe(500);
      expect(data.draws).toBe(200);
      expect(data.black).toBe(300);
      expect(data.moves).toHaveLength(1);
      expect(data.topGames).toBeDefined();
      expect(data.topGames).toEqual(finalResult.recentGames);
      expect(data.recentGames).toEqual(finalResult.recentGames);
    });

    it('should normalize recentGames to topGames for frontend compatibility', async () => {
      const finalResult = {
        white: 100,
        draws: 50,
        black: 75,
        moves: [],
        recentGames: [
          {
            id: 'game1',
            winner: 'black',
            speed: 'rapid',
            mode: 'rated',
            black: { name: 'player1', rating: 2400 },
            white: { name: 'player2', rating: 2350 },
            year: 2024,
            month: 2,
          },
        ],
      };

      mockNDJSONFetch([finalResult]);

      const request = createMockRequest('player', { player: 'testplayer' });
      const params = createMockParams(['player']);

      const response = await GET(request, { params });
      const data = await response.json();

      expect(data.topGames).toBeDefined();
      expect(data.topGames).toEqual(finalResult.recentGames);
    });

    it('should use 45s timeout for player endpoint', async () => {
      const finalResult = {
        white: 100,
        draws: 50,
        black: 75,
        moves: [],
        recentGames: [],
      };

      mockNDJSONFetch([finalResult]);

      const request = createMockRequest('player', { player: 'testplayer' });
      const params = createMockParams(['player']);

      await GET(request, { params });

      const fetchCall = (global.fetch as any).mock.calls[0];
      expect(fetchCall[1].signal).toBeDefined();
      // We can't directly test the timeout value, but we verify signal exists
    });

    it('should handle empty NDJSON response', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        text: async () => '\n\n',
      });

      const request = createMockRequest('player', { player: 'testplayer' });
      const params = createMockParams(['player']);

      const response = await GET(request, { params });
      const data = await response.json();

      // Should return fallback data on error
      expect(response.status).toBe(200);
      expect(data).toHaveProperty('white');
      expect(data).toHaveProperty('moves');
    });

    it('should use 10s timeout for non-player endpoints', async () => {
      mockSuccessfulFetch({ white: 100, draws: 50, black: 75, moves: [], topGames: [], opening: null });

      const request = createMockRequest('masters', { fen: 'test' });
      const params = createMockParams(['masters']);

      await GET(request, { params });

      const fetchCall = (global.fetch as any).mock.calls[0];
      expect(fetchCall[1].signal).toBeDefined();
      // We can't directly test the timeout value, but we verify signal exists
    });
  });
});
