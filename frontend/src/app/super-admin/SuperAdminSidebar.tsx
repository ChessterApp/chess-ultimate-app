'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

interface NavItem {
  href: string;
  label: string;
  badge?: string;
  enabled: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { href: '/super-admin', label: 'Overview', enabled: true },
  { href: '/super-admin/users', label: 'Users', enabled: true },
  { href: '/super-admin/schools', label: 'Schools', enabled: true },
  { href: '/super-admin/audit', label: 'Audit log', badge: 'Phase 7D', enabled: false },
];

export default function SuperAdminSidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden md:flex flex-col w-64 border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
      <div className="px-6 py-5 border-b border-gray-200 dark:border-gray-700">
        <span className="block text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Chesster
        </span>
        <span className="block text-sm font-semibold text-gray-900 dark:text-gray-100">
          Platform Admin
        </span>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_ITEMS.map((item) => {
          const isActive =
            pathname === item.href ||
            (item.href !== '/super-admin' && pathname?.startsWith(item.href + '/'));
          const baseClasses =
            'flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition-colors';
          if (!item.enabled) {
            return (
              <span
                key={item.href}
                className={`${baseClasses} text-gray-400 dark:text-gray-500 cursor-not-allowed`}
                aria-disabled
              >
                <span>{item.label}</span>
                {item.badge && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-200 dark:bg-gray-700">
                    {item.badge}
                  </span>
                )}
              </span>
            );
          }
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`${baseClasses} ${
                isActive
                  ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
              }`}
            >
              <span>{item.label}</span>
              {item.badge && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-200 dark:bg-gray-700">
                  {item.badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="px-3 py-4 border-t border-gray-200 dark:border-gray-700">
        <Link
          href="/dashboard"
          className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
        >
          <span>← Back to App</span>
        </Link>
      </div>
    </aside>
  );
}
