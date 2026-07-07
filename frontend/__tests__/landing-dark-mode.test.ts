import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

const read = (rel: string) => readFileSync(join(__dirname, '..', rel), 'utf8')

const page = read('src/app/page.tsx')
const heroButtons = read('src/components/landing/HeroButtons.tsx')
const css = read('src/app/globals.css')

describe('landing page dark-mode repaint fix', () => {
  it('marks the landing page root with the landing-light class', () => {
    expect(page).toMatch(/<main className="landing-light[^"]*bg-white/)
  })

  it('keeps the blanket html.dark overrides intact (other pages depend on them)', () => {
    expect(css).toMatch(/html\.dark \.bg-white \{ background-color: #1a1a1a !important; \}/)
    expect(css).toMatch(/html\.dark \.text-purple-700 \{ color: #a78bfa !important; \}/)
  })

  // Every blanket-overridden utility class actually used on the landing page
  // must have a matching html.dark .landing-light counter-override that restores
  // its original light value. Keep this list in sync with page.tsx / HeroButtons.tsx.
  const counters: Record<string, RegExp> = {
    'bg-white': /html\.dark \.landing-light \.bg-white \{ background-color: #ffffff !important; \}/,
    'bg-gray-50': /html\.dark \.landing-light \.bg-gray-50 \{ background-color: #f9fafb !important; \}/,
    'text-gray-800': /html\.dark \.landing-light \.text-gray-800 \{ color: #1f2937 !important; \}/,
    'text-gray-600': /html\.dark \.landing-light \.text-gray-600 \{ color: #4b5563 !important; \}/,
    'text-gray-400': /html\.dark \.landing-light \.text-gray-400 \{ color: #9ca3af !important; \}/,
    'text-purple-700': /html\.dark \.landing-light \.text-purple-700 \{ color: #7e22ce !important; \}/,
    'text-purple-600': /html\.dark \.landing-light \.text-purple-600 \{ color: #9333ea !important; \}/,
    'border-gray-100': /html\.dark \.landing-light \.border-gray-100 \{ border-color: #f3f4f6 !important; \}/,
    'border-purple-200': /html\.dark \.landing-light \.border-purple-200 \{ border-color: #e9d5ff !important; \}/,
    'from-purple-600': /html\.dark \.landing-light \.from-purple-600 \{ --tw-gradient-from: #9333ea !important; \}/,
  }

  for (const [cls, re] of Object.entries(counters)) {
    it(`adds a scoped counter-override for .${cls}`, () => {
      expect(css).toMatch(re)
    })
  }

  it('scopes every counter-override under .landing-light (never weakens the blanket rules)', () => {
    const landingRules = css
      .split('\n')
      .filter((l) => l.includes('.landing-light'))
    expect(landingRules.length).toBeGreaterThanOrEqual(Object.keys(counters).length)
    for (const line of landingRules) {
      expect(line).toMatch(/^html\.dark \.landing-light /)
    }
  })
})
