'use client'

import { useRouter } from 'next/navigation'

export function ProductCard({ icon, title, description, color, href }: { icon: string, title: string, description: string, color: string, href: string }) {
  const router = useRouter()

  return (
    <button
      onClick={() => router.push(href)}
      className={`${color} rounded-2xl p-6 text-left hover:scale-105 transition-all duration-300 shadow-lg hover:shadow-2xl group w-full`}
    >
      <div className="text-4xl mb-3 group-hover:scale-110 transition-transform duration-300">{icon}</div>
      <h3 className="text-lg font-bold text-white mb-2">{title}</h3>
      <p className="text-white/80 text-sm">{description}</p>
    </button>
  )
}
