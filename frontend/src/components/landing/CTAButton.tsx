'use client'

import { useRouter } from 'next/navigation'

export function CTAButton({ href, children, className }: { href: string, children: React.ReactNode, className?: string }) {
  const router = useRouter()

  return (
    <button
      onClick={() => router.push(href)}
      className={className}
    >
      {children}
    </button>
  )
}
