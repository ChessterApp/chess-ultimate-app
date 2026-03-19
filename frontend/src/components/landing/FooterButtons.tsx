'use client'

import { useRouter } from 'next/navigation'

export function FooterButton({ href, children }: { href?: string, children: React.ReactNode }) {
  const router = useRouter()

  return (
    <button
      onClick={() => href && router.push(href)}
      className="hover:text-white transition-colors"
    >
      {children}
    </button>
  )
}
