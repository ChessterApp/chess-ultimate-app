'use client'

import Link from 'next/link'

export function ProductCard({ icon, title, description, color, href }: { icon: string, title: string, description: string, color: string, href: string }) {
  return (
    <Link
      href={href}
      prefetch={true}
      className={`${color} rounded-2xl p-6 text-left hover:scale-105 transition-all duration-300 shadow-lg hover:shadow-2xl group w-full block`}
    >
      <div className="text-4xl mb-3 group-hover:scale-110 transition-transform duration-300">{icon}</div>
      <h3 className="text-lg font-bold text-white mb-2">{title}</h3>
      <p className="text-white/80 text-sm">{description}</p>
    </Link>
  )
}
