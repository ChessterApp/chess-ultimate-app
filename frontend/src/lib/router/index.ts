// frontend/src/lib/router/index.ts
// Hybrid routing logic for Mastra (quick analysis) vs Clawdbot (deep coaching)

export type RouteTarget = 'mastra' | 'clawdbot' | 'chesster';

export interface RouteContext {
  fen?: string;
  hasGameHistory?: boolean;
  isNewUser?: boolean;
  explicitCoaching?: boolean;
}

// Keywords that indicate need for deep coaching (Clawdbot)
const CLAWDBOT_KEYWORDS = [
  'review', 'lesson', 'study', 'progress', 'improve',
  'generate', 'create', 'plan', 'history', 'remember',
  'last game', 'my games', 'weakness', 'strength',
  'teach me', 'learning', 'practice', 'training',
  'long term', 'over time', 'pattern', 'habit'
];

// Keywords that indicate need for quick position analysis (Mastra)
const MASTRA_KEYWORDS = [
  'best move', 'evaluate', 'this position', 'should I',
  'what if', 'explain move', 'check', 'threat', 'tactic',
  'right now', 'current', 'analyze', 'calculate'
];

/**
 * Determines whether a request should be routed to Mastra or Clawdbot
 * based on query content and context.
 * 
 * @param query - The user's question or request
 * @param context - Additional context about the request
 * @returns 'mastra' for quick analysis, 'clawdbot' for deep coaching
 */
export function routeRequest(query: string, context: RouteContext = {}): RouteTarget {
  const queryLower = query.toLowerCase();

  // Explicit coaching request flag takes precedence
  if (context.explicitCoaching) {
    return 'clawdbot';
  }

  // Check for Clawdbot keywords first (they indicate coaching needs)
  for (const keyword of CLAWDBOT_KEYWORDS) {
    if (queryLower.includes(keyword)) {
      return 'clawdbot';
    }
  }

  // Check for Mastra keywords (position-specific analysis)
  for (const keyword of MASTRA_KEYWORDS) {
    if (queryLower.includes(keyword)) {
      return 'mastra';
    }
  }

  // If no position context and asking general questions, use Clawdbot
  if (!context.fen && !hasPositionReference(queryLower)) {
    // General improvement questions go to coaching
    if (queryLower.includes('how') || queryLower.includes('why')) {
      return 'clawdbot';
    }
  }

  // Default to Mastra for speed
  return 'mastra';
}

/**
 * Check if query references a specific chess position
 */
function hasPositionReference(query: string): boolean {
  const positionWords = [
    'position', 'move', 'piece', 'pawn', 'knight', 'bishop',
    'rook', 'queen', 'king', 'square', 'rank', 'file',
    'e4', 'd4', 'c4', 'nf3', 'castle', 'capture'
  ];
  return positionWords.some(word => query.includes(word));
}

/**
 * Get a user-friendly explanation of the routing decision
 */
export function getRouteExplanation(target: RouteTarget, _query: string): string {
  if (target === 'clawdbot') {
    return 'Using deep coaching for personalized response...';
  }
  return 'Using quick analysis...';
}

/**
 * Utility to check if Clawdbot is available
 */
export function isClawdbotAvailable(): boolean {
  return !!(process.env.CLAWDBOT_GATEWAY_URL || process.env.CLAWDBOT_GATEWAY_TOKEN);
}

/**
 * Utility to check if Chesster gateway is available
 */
export function isChessterAvailable(): boolean {
  return !!(
    process.env.CLAWDBOT_GATEWAY_URL &&
    process.env.CLAWDBOT_GATEWAY_TOKEN &&
    process.env.CHESSTER_GATEWAY_ENABLED === 'true'
  );
}

/**
 * Fallback to Clawdbot gateway when Mastra (and all its retries) have failed.
 * This is a last-resort safety net.
 */
export async function fallbackToClawdbot(
  query: string,
  fen: string,
  userId: string
): Promise<{ success: boolean; message: string; route: 'clawdbot-fallback' }> {
  // Dynamic import to avoid pulling gateway code into client bundles
  const { callGateway } = await import('@/lib/clawdbot/gateway');

  const response = await callGateway(userId, {
    action: 'chat',
    payload: {
      message: query,
      fen,
    },
    timeout: 60000,
  });

  if (response.success && response.content) {
    return {
      success: true,
      message: response.content,
      route: 'clawdbot-fallback',
    };
  }

  return {
    success: false,
    message: response.error || 'Both Mastra and Clawdbot fallback failed.',
    route: 'clawdbot-fallback',
  };
}
