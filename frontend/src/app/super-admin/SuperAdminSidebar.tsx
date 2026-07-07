'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect } from 'react';

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

interface SuperAdminSidebarProps {
  mobileOpen?: boolean;
  onClose?: () => void;
}

export default function SuperAdminSidebar({ mobileOpen = false, onClose }: SuperAdminSidebarProps) {
  const pathname = usePathname();

  useEffect(() => {
    if (!mobileOpen || typeof document === 'undefined') return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [mobileOpen]);

  const navBody = (
    <>
      <div className="px-6 py-5 border-b border-gray-200 dark:border-gray-700">
        <span className="block text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Chesster
        </span>
        <span className="block text-sm font-semibold text-gray-900 dark:text-gray-100">
          Platform Admin
        </span>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
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
              onClick={onClose}
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
          onClick={onClose}
          className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
        >
          <span>← Back to App</span>
        </Link>
      </div>
    </>
  );

  return (
    <>
      <aside className="hidden md:flex flex-col w-64 border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
        {navBody}
      </aside>

      {mobileOpen && (
        <div
          className="md:hidden fixed inset-0 z-40 bg-black/50"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
      <aside
        className={`md:hidden fixed inset-y-0 left-0 z-50 flex flex-col w-64 max-w-[80vw] border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-xl transform transition-transform duration-200 ease-in-out ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
        aria-hidden={!mobileOpen}
      >
        {navBody}
      </aside>
    </>
  );
}
