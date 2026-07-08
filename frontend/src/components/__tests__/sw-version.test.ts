import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

describe('Service Worker', () => {
  const swContent = readFileSync(resolve(__dirname, '../../../public/sw.js'), 'utf-8');

  it('should have cache version 13', () => {
    expect(swContent).toContain("const CACHE_VERSION = '13'");
  });

  it('should use stale-while-revalidate for Lichess Explorer (5min TTL)', () => {
    expect(swContent).toContain('EXPLORER_TTL');
    expect(swContent).toContain('5 * 60 * 1000');
  });

  it('should use stale-while-revalidate for Chess.com API (10min TTL)', () => {
    expect(swContent).toContain('CHESSCOM_TTL');
    expect(swContent).toContain('10 * 60 * 1000');
  });

  it('should use cache-first for TWIC games (immutable)', () => {
    expect(swContent).toContain('isTwicGames');
    expect(swContent).toContain('cacheFirst');
  });

  it('should use network-only for AI chat streams', () => {
    expect(swContent).toContain('isAiChatStream');
    expect(swContent).toContain('networkOnly');
  });

  it('should exclude WASM and engine files from caching', () => {
    expect(swContent).toContain('.wasm');
    expect(swContent).toContain('/static/engine/');
  });

  it('should cache Maia .onnx model files cache-first', () => {
    expect(swContent).toContain('isMaiaModel');
    expect(swContent).toContain(".onnx");
  });

  it('should clean up old caches on activation', () => {
    expect(swContent).toContain('caches.keys()');
    expect(swContent).toContain('caches.delete');
  });
});
