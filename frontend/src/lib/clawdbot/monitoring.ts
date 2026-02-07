// frontend/src/lib/clawdbot/monitoring.ts
// Monitoring, logging, and input validation for coaching endpoints

import type { RouteTarget } from '@/lib/router';
import type { CoachingRequest, CoachingAction } from './types';

// ─── Metrics Tracking ───────────────────────────────────────────────────────

interface RequestMetric {
  route: RouteTarget;
  action: string;
  latencyMs: number;
  success: boolean;
  userId: string;
  timestamp: number;
  tokensUsed?: number;
  error?: string;
}

const metrics: RequestMetric[] = [];
const MAX_METRICS = 1000;

export function recordMetric(metric: RequestMetric): void {
  metrics.push(metric);
  if (metrics.length > MAX_METRICS) metrics.shift();

  const level = metric.success ? 'info' : 'error';
  const tag = `[coaching:${metric.route}:${metric.action}]`;
  const msg = `${tag} ${metric.latencyMs}ms success=${metric.success} user=${metric.userId.slice(0, 12)}`;
  if (level === 'error') {
    console.error(msg, metric.error);
  } else {
    console.log(msg);
  }
}

export function getMetricsSummary() {
  const now = Date.now();
  const last24h = metrics.filter((m) => now - m.timestamp < 86400000);

  const byRoute: Record<RouteTarget, number> = { mastra: 0, clawdbot: 0, chesster: 0 };
  let totalLatency = 0;
  let errors = 0;
  const tokensByUser: Record<string, number> = {};

  for (const m of last24h) {
    byRoute[m.route]++;
    totalLatency += m.latencyMs;
    if (!m.success) errors++;
    if (m.tokensUsed) {
      tokensByUser[m.userId] = (tokensByUser[m.userId] || 0) + m.tokensUsed;
    }
  }

  return {
    total: last24h.length,
    routeDistribution: byRoute,
    avgLatencyMs: last24h.length ? Math.round(totalLatency / last24h.length) : 0,
    errorRate: last24h.length ? +(errors / last24h.length).toFixed(3) : 0,
    tokensByUser,
  };
}

// ─── Logging Helper ─────────────────────────────────────────────────────────

export function logCoaching(endpoint: string, userId: string, action: string, extra?: Record<string, unknown>): void {
  console.log(`[coaching:${endpoint}] user=${userId.slice(0, 12)} action=${action}`, extra || '');
}

// ─── Timed Execution ────────────────────────────────────────────────────────

export async function timedExec<T>(
  route: RouteTarget,
  action: string,
  userId: string,
  fn: () => Promise<T>
): Promise<{ result: T; latencyMs: number }> {
  const start = Date.now();
  try {
    const result = await fn();
    const latencyMs = Date.now() - start;
    recordMetric({ route, action, latencyMs, success: true, userId, timestamp: start });
    return { result, latencyMs };
  } catch (error) {
    const latencyMs = Date.now() - start;
    recordMetric({
      route, action, latencyMs, success: false, userId, timestamp: start,
      error: error instanceof Error ? error.message : String(error),
    });
    throw error;
  }
}

// ─── Input Validation ───────────────────────────────────────────────────────

interface ValidationResult {
  valid: boolean;
  error?: string;
}

const VALID_ACTIONS: CoachingAction[] = ['chat', 'review-game', 'generate-lesson', 'get-progress', 'update-profile'];

export function validatePgn(pgn: string): ValidationResult {
  if (!pgn || pgn.trim().length === 0) return { valid: false, error: 'PGN is empty' };
  if (pgn.length > 100000) return { valid: false, error: 'PGN exceeds 100KB limit' };
  // Basic sanity: should contain at least one move number
  if (!/\d+\./.test(pgn) && !/\[.*\]/.test(pgn)) {
    return { valid: false, error: 'PGN does not appear to contain valid move data or headers' };
  }
  return { valid: true };
}

export function validateFen(fen: string): ValidationResult {
  if (!fen || fen.trim().length === 0) return { valid: false, error: 'FEN is empty' };
  const parts = fen.trim().split(/\s+/);
  if (parts.length < 2) return { valid: false, error: 'FEN must have at least piece placement and active color' };
  // Piece placement should have 8 ranks separated by /
  const ranks = parts[0].split('/');
  if (ranks.length !== 8) return { valid: false, error: 'FEN piece placement must have 8 ranks' };
  // Active color
  if (!['w', 'b'].includes(parts[1])) return { valid: false, error: 'FEN active color must be w or b' };
  return { valid: true };
}

export function validateQueryLength(query: string, maxLength = 10000): ValidationResult {
  if (!query || query.trim().length === 0) return { valid: false, error: 'Query is empty' };
  if (query.length > maxLength) return { valid: false, error: `Query exceeds ${maxLength} character limit` };
  return { valid: true };
}

export function validateCoachingRequest(request: Partial<CoachingRequest>): ValidationResult {
  if (!request.action) return { valid: false, error: 'Missing action field' };
  if (!VALID_ACTIONS.includes(request.action as CoachingAction)) {
    return { valid: false, error: `Invalid action: ${request.action}. Valid: ${VALID_ACTIONS.join(', ')}` };
  }
  return { valid: true };
}
