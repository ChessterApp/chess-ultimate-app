'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { ChevronRight, Home } from 'lucide-react'

interface BreadcrumbItem {
  label: string
  href?: string
}

interface BreadcrumbsProps {
  items?: BreadcrumbItem[]
  className?: string
}

const ROUTE_LABELS: Record<string, string> = {
  learn: 'Courses',
  puzzle: 'Puzzles',
  position: 'Analysis',
  analyze: 'Analysis',
  game: 'Game Review',
  dashboard: 'Dashboard',
  profile: 'Profile',
  settings: 'Settings',
  database: 'Openings',
  editor: 'Board Editor',
  opponent: 'Opponent Prep',
}

export default function Breadcrumbs({ items, className = '' }: BreadcrumbsProps) {
  const pathname = usePathname() ?? ''

  const breadcrumbs: BreadcrumbItem[] = items || (() => {
    const segments = pathname.split('/').filter(Boolean)
    const crumbs: BreadcrumbItem[] = []

    let path = ''
    for (let i = 0; i < segments.length; i++) {
      path += `/${segments[i]}`
      const label = ROUTE_LABELS[segments[i]] || decodeURIComponent(segments[i]).replace(/-/g, ' ')
      const isLast = i === segments.length - 1
      crumbs.push({
        label: label.charAt(0).toUpperCase() + label.slice(1),
        href: isLast ? undefined : path,
      })
    }
    return crumbs
  })()

  if (breadcrumbs.length <= 0) return null

  return (
    <nav aria-label="Breadcrumb" className={`flex items-center gap-1.5 text-xs text-gray-400 mb-3 ${className}`}>
      <Link href="/dashboard" className="hover:text-gray-600 transition-colors">
        <Home className="w-3.5 h-3.5" />
      </Link>
      {breadcrumbs.map((crumb, i) => (
        <span key={i} className="flex items-center gap-1.5">
          <ChevronRight className="w-3 h-3 text-gray-300" />
          {crumb.href ? (
            <Link href={crumb.href} className="hover:text-gray-600 transition-colors">
              {crumb.label}
            </Link>
          ) : (
            <span className="text-gray-500 font-medium">{crumb.label}</span>
          )}
        </span>
      ))}
    </nav>
  )
}
