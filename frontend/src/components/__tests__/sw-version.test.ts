import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

describe('Service Worker', () => {
  const swContent = readFileSync(resolve(__dirname, '../../../public/sw.js'), 'utf-8');

  it('should have cache version 16', () => {
    expect(swContent).toContain("const CACHE_VERSION = '16'");
  });

  it('should only cache successful responses in networkFirst (no 4xx/5xx)', () => {
    expect(swContent).toMatch(/function networkFirst[\s\S]*if \(response\.ok\)/);
  });

  it('should serve RSC payload fetches network-first (not stale cache)', () => {
    expect(swContent).toContain('function isRscRequest');
    expect(swContent).toContain("request.headers.get('RSC')");
    expect(swContent).toContain("url.searchParams.has('_rsc')");
    expect(swContent).toMatch(
      /isRscRequest\(event\.request, url\)\)\s*\{\s*networkFirst\(event\)/,
    );
  });

  it('should use network-first (not cache-first) for the catch-all handler', () => {
    // The final fallthrough must be Network-First so returning users are never
    // pinned to a stale HTML/RSC page.
    expect(swContent).toMatch(/Everything else[\s\S]*networkFirst\(event\);\s*\}\);/);
    expect(swContent).not.toMatch(/Everything else[\s\S]*cacheFirst\(event\);\s*\}\);/);
  });

  it('should use stale-while-revalidate for Lichess Explorer (5min TTL)', () => {
    expect(swContent).toContain('EXPLORER_TTL');
    expect(swContent).toContain('5 * 60 * 1000');
  });

  it('should use stale-while-revalidate for Chess.com API (10min TTL)', () => {
    expect(swContent).toContain('CHESSCOM_TTL');
    expect(swContent).toContain('10 * 60 * 1000');
  });

  it('should use stale-while-revalidate for TWIC games (1h TTL — weekly imports add games)', () => {
    expect(swContent).toContain('isTwicGames');
    expect(swContent).toContain('TWIC_TTL');
    expect(swContent).toContain('60 * 60 * 1000');
    expect(swContent).not.toMatch(/isTwicGames\(url\)\)\s*\{\s*cacheFirst/);
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
