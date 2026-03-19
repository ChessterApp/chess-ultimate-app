'use client'

import Link from 'next/link'

export function FooterButton({ href, children }: { href?: string, children: React.ReactNode }) {
  if (!href) {
    return (
      <button className="hover:text-white transition-colors">
        {children}
      </button>
    )
  }

  return (
    <Link
      href={href}
      prefetch={true}
      className="hover:text-white transition-colors"
    >
      {children}
    </Link>
  )
}
