import { describe, it, expect, beforeEach } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

/**
 * Tests for service worker configuration.
 *
 * Verifies:
 * 1. Cache name is correctly versioned
 * 2. Install/activate lifecycle events
 * 3. Strategy routing: Cache-First, Network-First, Stale-While-Revalidate, Network-Only
 * 4. WASM, ONNX, and worker files excluded from interception
 * 5. Route-specific caching strategies for API endpoints
 */
describe('Service Worker', () => {
  let swContent: string

  beforeEach(() => {
    const swPath = join(process.cwd(), 'public', 'sw.js')
    swContent = readFileSync(swPath, 'utf-8')
  })

  it('defines a versioned cache name', () => {
    expect(swContent).toContain("const CACHE_VERSION = '")
    expect(swContent).toContain("const CACHE_NAME = 'chesster-v' + CACHE_VERSION")
  })

  it('uses skipWaiting for immediate activation', () => {
    expect(swContent).toContain('self.skipWaiting()')
  })

  it('claims clients on activation', () => {
    expect(swContent).toContain('self.clients.claim()')
  })

  it('cleans up old caches on activation', () => {
    expect(swContent).toContain('caches.keys()')
    expect(swContent).toContain('caches.delete(k)')
  })

  it('only handles GET requests', () => {
    expect(swContent).toContain("if (event.request.method !== 'GET') return")
  })

  it('skips cross-origin requests', () => {
    expect(swContent).toContain('url.origin !== self.location.origin')
  })

  it('excludes WASM files from interception', () => {
    expect(swContent).toContain(".endsWith('.wasm')")
  })

  it('caches Maia .onnx model files cache-first', () => {
    expect(swContent).toContain('function isMaiaModel(url)')
    expect(swContent).toContain('isMaiaModel(url)')
    expect(swContent).toContain(".endsWith('.onnx')")
  })

  it('uses network-first for navigation requests', () => {
    expect(swContent).toContain("event.request.mode === 'navigate'")
  })

  it('returns 503 when offline and no cache available', () => {
    expect(swContent).toContain("new Response('Offline', { status: 503")
  })

  it('uses cache-first for static assets', () => {
    expect(swContent).toContain('caches.match(event.request)')
  })

  // Phase 3: Strategy routing tests
  describe('strategy routing', () => {
    it('has a staleWhileRevalidate strategy function', () => {
      expect(swContent).toContain('function staleWhileRevalidate(event, ttlMs)')
    })

    it('has a networkOnly strategy function', () => {
      expect(swContent).toContain('function networkOnly(event)')
    })

    it('has a cacheFirst strategy function', () => {
      expect(swContent).toContain('function cacheFirst(event)')
    })

    it('has a networkFirst strategy function', () => {
      expect(swContent).toContain('function networkFirst(event)')
    })

    it('routes Lichess Explorer to stale-while-revalidate with 5min TTL', () => {
      expect(swContent).toContain("url.pathname.startsWith('/api/explorer/')")
      expect(swContent).toContain('EXPLORER_TTL')
      expect(swContent).toContain('5 * 60 * 1000')
    })

    it('routes Chess.com API to stale-while-revalidate with 10min TTL', () => {
      expect(swContent).toContain("url.pathname.startsWith('/api/chesscom/')")
      expect(swContent).toContain('CHESSCOM_TTL')
      expect(swContent).toContain('10 * 60 * 1000')
    })

    it('routes TWIC game queries to cache-first', () => {
      expect(swContent).toContain("url.pathname === '/api/openings/games/by-position'")
    })

    it('routes AI chat streaming to network-only', () => {
      expect(swContent).toContain("url.pathname.startsWith('/api/chat/stream')")
      expect(swContent).toContain('networkOnly(event)')
    })

    it('routes Flask backend API to network-first', () => {
      expect(swContent).toContain("url.pathname.startsWith('/api/')")
      expect(swContent).toContain('networkFirst(event)')
    })

    it('routes static assets to cache-first', () => {
      expect(swContent).toContain('isStaticAsset(url)')
      expect(swContent).toContain('cacheFirst(event)')
    })

    it('stores cache timestamp for stale-while-revalidate', () => {
      expect(swContent).toContain("headers.set('sw-cache-time'")
      expect(swContent).toContain("cached.headers.get('sw-cache-time'")
    })
  })

  describe('static asset detection', () => {
    it('recognizes Next.js static assets', () => {
      expect(swContent).toContain("url.pathname.startsWith('/_next/static/')")
    })

    it('recognizes SVG files', () => {
      expect(swContent).toContain(".endsWith('.svg')")
    })

    it('recognizes image formats', () => {
      expect(swContent).toContain(".endsWith('.png')")
      expect(swContent).toContain(".endsWith('.jpg')")
      expect(swContent).toContain(".endsWith('.webp')")
    })

    it('recognizes CSS files', () => {
      expect(swContent).toContain(".endsWith('.css')")
    })
  })
})
