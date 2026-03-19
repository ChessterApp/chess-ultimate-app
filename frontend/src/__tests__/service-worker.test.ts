import { describe, it, expect, beforeEach, vi } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

/**
 * Tests for service worker precaching configuration.
 *
 * These tests verify that:
 * 1. Critical page shells are precached on service worker install
 * 2. The cache name is correctly versioned
 * 3. All expected routes are included in the SHELL_ASSETS array
 */
describe('Service Worker Precaching', () => {
  let swContent: string

  beforeEach(() => {
    // Read the service worker file
    const swPath = join(process.cwd(), 'public', 'sw.js')
    swContent = readFileSync(swPath, 'utf-8')
  })

  it('defines the correct cache version', () => {
    expect(swContent).toContain("const CACHE_NAME = 'chesster-v5'")
  })

  it('precaches the homepage', () => {
    expect(swContent).toContain("'/'")
  })

  it('precaches the dashboard page', () => {
    expect(swContent).toContain("'/dashboard'")
  })

  it('precaches the debut page', () => {
    expect(swContent).toContain("'/debut'")
  })

  it('precaches the learn page', () => {
    expect(swContent).toContain("'/learn'")
  })

  it('precaches the puzzle page', () => {
    expect(swContent).toContain("'/puzzle'")
  })

  it('includes all critical shell assets in SHELL_ASSETS array', () => {
    const criticalPages = ['/', '/dashboard', '/debut', '/learn', '/puzzle']

    // Extract SHELL_ASSETS array from the service worker content
    const shellAssetsMatch = swContent.match(/const SHELL_ASSETS = \[([\s\S]*?)\];/)
    expect(shellAssetsMatch).toBeTruthy()

    if (shellAssetsMatch) {
      const shellAssetsContent = shellAssetsMatch[1]

      // Verify each critical page is in the SHELL_ASSETS
      for (const page of criticalPages) {
        expect(shellAssetsContent).toContain(`'${page}'`)
      }
    }
  })

  it('uses skipWaiting for immediate activation', () => {
    expect(swContent).toContain('self.skipWaiting()')
  })

  it('claims clients on activation', () => {
    expect(swContent).toContain('self.clients.claim()')
  })

  it('implements stale-while-revalidate for navigation requests', () => {
    expect(swContent).toContain("if (event.request.mode === 'navigate')")
    expect(swContent).toContain('caches.match(event.request)')
  })
})

describe('Service Worker Registration Component', () => {
  it('uses the correct cache buster version', async () => {
    const { readFileSync } = await import('fs')
    const { join } = await import('path')

    const registrationPath = join(process.cwd(), 'src', 'components', 'ServiceWorkerRegistration.tsx')
    const registrationContent = readFileSync(registrationPath, 'utf-8')

    // Verify the cache buster version matches the service worker version
    expect(registrationContent).toContain("navigator.serviceWorker.register('/sw.js?v=4'")
  })
})
