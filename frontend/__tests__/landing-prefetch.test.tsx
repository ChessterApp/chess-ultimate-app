/**
 * @vitest-environment jsdom
 */
import { render } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { PrefetchLinks } from '@/components/landing/PrefetchLinks'
import { ProductCard } from '@/components/landing/ProductCard'
import { FooterButton } from '@/components/landing/FooterButtons'

describe('Landing Page Prefetch Links', () => {
  it('PrefetchLinks renders hidden links with prefetch for main routes', () => {
    const { container } = render(<PrefetchLinks />)

    // Check for hidden container
    const hiddenDiv = container.querySelector('div[style*="display: none"]')
    expect(hiddenDiv).toBeTruthy()

    // Check for prefetch links
    const links = container.querySelectorAll('a')
    const hrefs = Array.from(links).map(link => link.getAttribute('href'))

    expect(hrefs).toContain('/dashboard')
    expect(hrefs).toContain('/debut')
    expect(hrefs).toContain('/learn')
    expect(hrefs).toContain('/puzzle')
  })

  it('ProductCard renders Link component with prefetch', () => {
    const { container } = render(
      <ProductCard
        icon="📚"
        title="Test Card"
        description="Test Description"
        color="bg-purple-500"
        href="/learn"
      />
    )

    const link = container.querySelector('a[href="/learn"]')
    expect(link).toBeTruthy()
  })

  it('FooterButton renders Link component with prefetch when href is provided', () => {
    const { container } = render(
      <FooterButton href="/puzzle">Puzzles</FooterButton>
    )

    const link = container.querySelector('a[href="/puzzle"]')
    expect(link).toBeTruthy()
  })

  it('FooterButton renders button when no href is provided', () => {
    const { container } = render(
      <FooterButton>No Link</FooterButton>
    )

    const button = container.querySelector('button')
    expect(button).toBeTruthy()
    expect(button?.textContent).toBe('No Link')
  })
})
