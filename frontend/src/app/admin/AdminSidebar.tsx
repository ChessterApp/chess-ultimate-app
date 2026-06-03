'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect } from 'react';
import { useBranding } from '@/contexts/OrganizationContext';

type MemberRole = 'owner' | 'admin' | 'teacher' | 'student';

interface NavItem {
  href: string;
  label: string;
  icon: string;
  roles: MemberRole[];
}

const NAV_ITEMS: NavItem[] = [
  { href: '/admin/dashboard', label: 'Dashboard', icon: '📊', roles: ['owner', 'admin', 'teacher'] },
  { href: '/admin/students', label: 'Students', icon: '👥', roles: ['owner', 'admin', 'teacher'] },
  { href: '/admin/courses', label: 'Courses', icon: '📚', roles: ['owner', 'admin'] },
  { href: '/admin/settings', label: 'Settings', icon: '⚙️', roles: ['owner', 'admin'] },
  { href: '/admin/settings/domain', label: 'Custom Domain', icon: '🌐', roles: ['owner', 'admin'] },
  { href: '/admin/settings/sender-domain', label: 'Sender Domain', icon: '✉️', roles: ['owner', 'admin'] },
  { href: '/admin/settings/team', label: 'Team & Ownership', icon: '🤝', roles: ['owner'] },
  { href: '/admin/settings/branches', label: 'Branches', icon: '🏢', roles: ['owner', 'admin'] },
  { href: '/admin/analytics', label: 'Analytics', icon: '📈', roles: ['owner', 'admin', 'teacher'] },
  { href: '/admin/billing', label: 'Billing', icon: '💳', roles: ['owner'] },
  { href: '/admin/tournaments', label: 'Tournaments', icon: '🏆', roles: ['owner', 'admin'] },
];

interface AdminSidebarProps {
  currentRole: MemberRole;
  mobileOpen?: boolean;
  onClose?: () => void;
}

export default function AdminSidebar({ currentRole, mobileOpen = false, onClose }: AdminSidebarProps) {
  const pathname = usePathname();
  const branding = useBranding();

  const visibleItems = NAV_ITEMS.filter(item => item.roles.includes(currentRole));

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
      <div className="flex items-center gap-3 px-6 py-5 border-b border-gray-200 dark:border-gray-700">
        {branding.logoUrl ? (
          <img src={branding.logoUrl} alt={branding.name} className="h-8 w-8 rounded" />
        ) : (
          <div
            className="h-8 w-8 rounded flex items-center justify-center text-white font-bold text-sm"
            style={{ backgroundColor: 'var(--brand-primary)' }}
          >
            {branding.name.charAt(0)}
          </div>
        )}
        <div className="flex flex-col min-w-0">
          <span className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
            {branding.name}
          </span>
          <span className="text-xs text-gray-500 dark:text-gray-400">Admin Panel</span>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {visibleItems.map(item => {
          const isActive = pathname === item.href || pathname?.startsWith(item.href + '/');
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onClose}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
              }`}
              style={isActive ? { color: 'var(--brand-primary)' } : undefined}
            >
              <span className="text-base">{item.icon}</span>
              <span>{item.label}</span>
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
          <span className="text-base">←</span>
          <span>Back to App</span>
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
