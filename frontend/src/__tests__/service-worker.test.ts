import { describe, it, expect, beforeEach } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

/**
 * Tests for service worker configuration.
 *
 * These tests verify that:
 * 1. The cache name is correctly versioned
 * 2. The service worker correctly handles install and activate events
 * 3. Network-first strategy is used for navigation, API, and Next.js assets
 * 4. WASM, ONNX, and worker files are excluded from interception
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

  it('excludes WASM and ONNX files from interception', () => {
    expect(swContent).toContain(".endsWith('.wasm')")
    expect(swContent).toContain(".endsWith('.onnx')")
  })

  it('uses network-first for navigation requests', () => {
    expect(swContent).toContain("event.request.mode === 'navigate'")
    expect(swContent).toContain('caches.match(event.request)')
  })

  it('uses network-first for API and Next.js assets', () => {
    expect(swContent).toContain("event.request.url.includes('/api/')")
    expect(swContent).toContain("event.request.url.includes('/_next/')")
  })

  it('returns 503 when offline and no cache available for navigation', () => {
    expect(swContent).toContain("new Response('Offline', { status: 503")
  })

  it('uses cache-first for static assets', () => {
    // The second respondWith block handles static assets with cache-first
    expect(swContent).toContain('caches.match(event.request).then((cached)')
  })
})
