import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { NextApiRequest, NextApiResponse } from 'next';

// Mock the agent module
vi.mock('@/server/mastra/agents', () => ({
  chessChesster: {
    generate: vi.fn(async () => ({
      text: 'This is a test response from the chess agent.',
      usage: { totalTokens: 100 }
    }))
  }
}));

// Mock the Clerk auth
vi.mock('@clerk/nextjs/server', () => ({
  getAuth: vi.fn(() => ({ userId: 'test-user-id' }))
}));

// Mock the board state and prompter
vi.mock('@/server/mastra/tools/protocol/state', () => ({
  getBoardState: vi.fn(() => ({
    validfen: true,
    fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
  }))
}));

vi.mock('@/server/mastra/tools/protocol/positionPrompter', () => {
  class MockPositionPrompter {
    generatePrompt() {
      return 'Position analysis prompt';
    }
  }
  return {
    PositionPrompter: MockPositionPrompter
  };
});

describe('API Route: /api/agent', () => {
  let mockReq: Partial<NextApiRequest>;
  let mockRes: Partial<NextApiResponse>;

  beforeEach(() => {
    vi.clearAllMocks();

    mockReq = {
      method: 'POST',
      body: {
        query: 'What is the best move in this position?',
        fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
        mode: 'position',
        apiSettings: {
          provider: 'google',
          model: 'gemini-2.5-flash',
          apiKey: 'test-api-key',
          isRouted: false,
          language: 'English'
        }
      }
    };

    mockRes = {
      status: vi.fn().mockReturnThis(),
      json: vi.fn().mockReturnThis()
    };
  });

  it('should successfully process a chess analysis request', async () => {
    const handler = (await import('@/pages/api/agent')).default;

    await handler(
      mockReq as NextApiRequest,
      mockRes as NextApiResponse
    );

    expect(mockRes.status).toHaveBeenCalledWith(200);
    expect(mockRes.json).toHaveBeenCalledWith(
      expect.objectContaining({
        message: expect.any(String),
        maxTokens: expect.any(Number),
        provider: 'google',
        model: 'gemini-2.5-flash'
      })
    );
  });

  it('should reject requests without required fields', async () => {
    const handler = (await import('@/pages/api/agent')).default;

    mockReq.body = {
      query: 'What is the best move?'
      // Missing fen, mode, apiSettings
    };

    await handler(
      mockReq as NextApiRequest,
      mockRes as NextApiResponse
    );

    expect(mockRes.status).toHaveBeenCalledWith(400);
  });

  it('should only accept POST requests', async () => {
    const handler = (await import('@/pages/api/agent')).default;

    mockReq.method = 'GET';

    await handler(
      mockReq as NextApiRequest,
      mockRes as NextApiResponse
    );

    expect(mockRes.status).toHaveBeenCalledWith(405);
  });
});
