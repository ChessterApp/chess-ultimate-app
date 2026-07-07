'use client';

import { usePathname } from 'next/navigation';
import PrefetchLink from '@/components/PrefetchLink';
import { ReactNode } from 'react';
import { useTranslations } from 'next-intl';

interface NavItem {
  href: string;
  labelKey: 'home' | 'playBot' | 'coach' | 'database' | 'profile';
  icon: ReactNode;
  activeIcon?: ReactNode;
}

const navItems: NavItem[] = [
  {
    href: '/dashboard',
    labelKey: 'home',
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
    ),
    activeIcon: (
      <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
        <path d="M11.47 3.84a.75.75 0 011.06 0l8.69 8.69a.75.75 0 101.06-1.06l-8.689-8.69a2.25 2.25 0 00-3.182 0l-8.69 8.69a.75.75 0 001.061 1.06l8.69-8.69z" />
        <path d="M12 5.432l8.159 8.159c.03.03.06.058.091.086v6.198c0 1.035-.84 1.875-1.875 1.875H15a.75.75 0 01-.75-.75v-4.5a.75.75 0 00-.75-.75h-3a.75.75 0 00-.75.75V21a.75.75 0 01-.75.75H5.625a1.875 1.875 0 01-1.875-1.875v-6.198a2.29 2.29 0 00.091-.086L12 5.43z" />
      </svg>
    ),
  },
  {
    href: '/play',
    labelKey: 'playBot',
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6V3.75m0 0a.75.75 0 100-1.5.75.75 0 000 1.5zM6.75 6h10.5a2.25 2.25 0 012.25 2.25v7.5a2.25 2.25 0 01-2.25 2.25H6.75a2.25 2.25 0 01-2.25-2.25v-7.5A2.25 2.25 0 016.75 6zM9 12h.008v.008H9V12zm6 0h.008v.008H15V12zM9.75 15.75h4.5" />
      </svg>
    ),
    activeIcon: (
      <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
        <path fillRule="evenodd" d="M11.25 3a.75.75 0 011.5 0v.087A2.251 2.251 0 0117.25 6H6.75A2.25 2.25 0 004.5 8.25v7.5A2.25 2.25 0 006.75 18h10.5a2.25 2.25 0 002.25-2.25v-7.5A2.25 2.25 0 0017.25 6a2.251 2.251 0 00-4.5-1.913V3a.75.75 0 00-1.5 0zM9 10.5a1.125 1.125 0 100 2.25 1.125 1.125 0 000-2.25zm6 0a1.125 1.125 0 100 2.25 1.125 1.125 0 000-2.25zm-5.25 4.5a.75.75 0 000 1.5h4.5a.75.75 0 000-1.5h-4.5z" clipRule="evenodd" />
      </svg>
    ),
  },
  {
    href: '/coach',
    labelKey: 'coach',
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
      </svg>
    ),
    activeIcon: (
      <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
        <path fillRule="evenodd" d="M9 4.5a.75.75 0 01.721.544l.813 2.846a3.75 3.75 0 002.576 2.576l2.846.813a.75.75 0 010 1.442l-2.846.813a3.75 3.75 0 00-2.576 2.576l-.813 2.846a.75.75 0 01-1.442 0l-.813-2.846a3.75 3.75 0 00-2.576-2.576l-2.846-.813a.75.75 0 010-1.442l2.846-.813A3.75 3.75 0 007.466 7.89l.813-2.846A.75.75 0 019 4.5zM18 1.5a.75.75 0 01.728.568l.258 1.036c.236.94.97 1.674 1.91 1.91l1.036.258a.75.75 0 010 1.456l-1.036.258c-.94.236-1.674.97-1.91 1.91l-.258 1.036a.75.75 0 01-1.456 0l-.258-1.036a2.625 2.625 0 00-1.91-1.91l-1.036-.258a.75.75 0 010-1.456l1.036-.258a2.625 2.625 0 001.91-1.91l.258-1.036A.75.75 0 0118 1.5zM16.5 15a.75.75 0 01.712.513l.394 1.183c.15.452.6.832 1.057.982l1.183.394a.75.75 0 010 1.428l-1.183.394c-.456.15-.907.53-1.057.982l-.394 1.183a.75.75 0 01-1.424 0l-.394-1.183a1.5 1.5 0 00-1.057-.982l-1.183-.394a.75.75 0 010-1.428l1.183-.394a1.5 1.5 0 001.057-.982l.394-1.183A.75.75 0 0116.5 15z" clipRule="evenodd" />
      </svg>
    ),
  },
  {
    href: '/database',
    labelKey: 'database',
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
      </svg>
    ),
    activeIcon: (
      <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
        <path d="M11.25 4.533A9.707 9.707 0 006 3a9.735 9.735 0 00-3.25.555.75.75 0 00-.5.707v14.25a.75.75 0 001 .707A8.237 8.237 0 016 18.75c1.995 0 3.823.707 5.25 1.886V4.533zM12.75 20.636A8.214 8.214 0 0118 18.75c.966 0 1.89.166 2.75.47a.75.75 0 001-.708V4.262a.75.75 0 00-.5-.707A9.735 9.735 0 0018 3a9.707 9.707 0 00-5.25 1.533v16.103z" />
      </svg>
    ),
  },
  {
    href: '/profile',
    labelKey: 'profile',
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
      </svg>
    ),
    activeIcon: (
      <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
        <path fillRule="evenodd" d="M7.5 6a4.5 4.5 0 119 0 4.5 4.5 0 01-9 0zM3.751 20.105a8.25 8.25 0 0116.498 0 .75.75 0 01-.437.695A18.683 18.683 0 0112 22.5c-2.786 0-5.433-.608-7.812-1.7a.75.75 0 01-.437-.695z" clipRule="evenodd" />
      </svg>
    ),
  },
];

interface BottomNavigationProps {
  className?: string;
}

export function BottomNavigation({ className = '' }: BottomNavigationProps) {
  const pathname = usePathname();
  const t = useTranslations('navigation');

  const isActive = (href: string) => {
    if (!pathname) return false;
    if (href === '/dashboard') {
      return pathname === '/' || pathname === '/dashboard';
    }
    if (href === '/database') {
      return pathname.startsWith('/database');
    }
    return pathname.startsWith(href);
  };

  return (
    <nav
      className={`fixed bottom-0 left-0 right-0 z-50 bg-white border-t border-gray-200 pb-safe md:hidden ${className}`}
    >
      <div className="flex items-center justify-around h-16">
        {navItems.map((item) => {
          const active = isActive(item.href);
          return (
            <PrefetchLink
              key={item.href}
              href={item.href}
              className={`flex flex-col items-center justify-center flex-1 h-full transition-colors ${
                active
                  ? 'text-purple-600'
                  : 'text-gray-500 hover:text-gray-700 active:text-purple-500'
              }`}
            >
              <div className={`${active ? 'scale-110' : ''} transition-transform`}>
                {active && item.activeIcon ? item.activeIcon : item.icon}
              </div>
              <span className={`text-xs mt-1 ${active ? 'font-semibold' : 'font-medium'}`}>
                {t(item.labelKey)}
              </span>
            </PrefetchLink>
          );
        })}
      </div>
    </nav>
  );
}

// Spacer component to prevent content from being hidden behind the nav
export function BottomNavSpacer() {
  return <div className="h-16 md:hidden" />;
}

// Floating action button variant for special actions
interface FloatingActionButtonProps {
  onClick: () => void;
  icon?: ReactNode;
  label?: string;
  className?: string;
}

export function FloatingActionButton({
  onClick,
  icon,
  label,
  className = '',
}: FloatingActionButtonProps) {
  return (
    <button
      onClick={onClick}
      className={`fixed bottom-20 right-4 z-40 flex items-center gap-2 bg-purple-600 text-white px-4 py-3 rounded-full shadow-lg hover:bg-purple-700 active:scale-95 transition-all md:bottom-4 ${className}`}
    >
      {icon || (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
        </svg>
      )}
      {label && <span className="font-medium">{label}</span>}
    </button>
  );
}
