'use client';

import { type ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import PrefetchLink from '@/components/PrefetchLink';
import { warmMaia } from '@/lib/engine/maiaSingleton';
import { useLocalStorage } from 'usehooks-ts';
import { useTranslations } from 'next-intl';
import { UserButton, useAuth } from '@clerk/nextjs';
import Image from 'next/image';
import { useState, useEffect } from 'react';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import { useLocale } from 'next-intl';
import { useBranding } from '@/contexts/OrganizationContext';

interface SidebarItem {
  href: string;
  labelKey: string;
  icon: ReactNode;
  activeIcon: ReactNode;
  shortcut?: string;
}

// Heroicons outline (inactive) and solid (active)
const items: SidebarItem[] = [
  {
    href: '/dashboard',
    labelKey: 'dashboard',
    shortcut: 'D',
    icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /></svg>,
    activeIcon: <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M11.47 3.84a.75.75 0 011.06 0l8.69 8.69a.75.75 0 101.06-1.06l-8.689-8.69a2.25 2.25 0 00-3.182 0l-8.69 8.69a.75.75 0 001.061 1.06l8.69-8.69z" /><path d="M12 5.432l8.159 8.159c.03.03.06.058.091.086v6.198c0 1.035-.84 1.875-1.875 1.875H15a.75.75 0 01-.75-.75v-4.5a.75.75 0 00-.75-.75h-3a.75.75 0 00-.75.75V21a.75.75 0 01-.75.75H5.625a1.875 1.875 0 01-1.875-1.875v-6.198a2.29 2.29 0 00.091-.086L12 5.43z" /></svg>,
  },
  {
    href: '/learn',
    labelKey: 'learn',
    shortcut: 'L',
    icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M4.26 10.147a60.438 60.438 0 00-.491 6.347A48.62 48.62 0 0112 20.904a48.62 48.62 0 018.232-4.41 60.46 60.46 0 00-.491-6.347m-15.482 0a50.636 50.636 0 00-2.658-.813A59.906 59.906 0 0112 3.493a59.903 59.903 0 0110.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0112 13.489a50.702 50.702 0 017.74-3.342M6.75 15a.75.75 0 100-1.5.75.75 0 000 1.5zm0 0v-3.675A55.378 55.378 0 0112 8.443m-7.007 11.55A5.981 5.981 0 006.75 15.75v-1.5" /></svg>,
    activeIcon: <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M11.7 2.805a.75.75 0 01.6 0A60.65 60.65 0 0122.83 8.72a.75.75 0 01-.231 1.337 49.949 49.949 0 00-9.902 3.912l-.003.002-.34.18a.75.75 0 01-.707 0A50.009 50.009 0 007.5 12.174v-.224c0-.131.067-.248.172-.311a.75.75 0 01.573-.084 48.96 48.96 0 015.38 2.001.75.75 0 10.582-1.228 50.451 50.451 0 00-6.956-2.528.75.75 0 01-.573-.084A1.117 1.117 0 006.5 9.879v-.224c0-.131.067-.248.172-.311l.003-.002.098-.052c1.5-.79 3.074-1.448 4.716-1.961a.75.75 0 10-.432-1.436 50.89 50.89 0 00-5.382 2.066.75.75 0 01-.573-.084A1.117 1.117 0 005 7.579v-.224c0-.131.067-.248.172-.311l.003-.002A60.618 60.618 0 0111.7 2.805z" /><path d="M13.06 15.473a48.45 48.45 0 017.666-3.282c.134 1.414.22 2.843.255 4.285a.75.75 0 01-.46.711 47.878 47.878 0 00-8.105 4.342.75.75 0 01-.832 0 47.877 47.877 0 00-8.104-4.342.75.75 0 01-.461-.71c.035-1.442.121-2.87.255-4.286A48.4 48.4 0 016 13.18v1.27a1.5 1.5 0 00-.14 2.508c-.09.38-.222.753-.397 1.11.452.213.901.434 1.346.661a6.729 6.729 0 00.551-1.608 1.5 1.5 0 00.14-2.67v-.645a48.549 48.549 0 013.44 1.668 2.25 2.25 0 002.12 0z" /><path d="M4.462 19.462c.42-.419.753-.89 1-1.394.453.213.902.434 1.347.661a6.743 6.743 0 01-1.286 1.794.75.75 0 11-1.06-1.06z" /></svg>,
  },
  {
    href: '/play',
    labelKey: 'playBot',
    shortcut: 'B',
    icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M12 6V3.75m0 0a.75.75 0 100-1.5.75.75 0 000 1.5zM6.75 6h10.5a2.25 2.25 0 012.25 2.25v7.5a2.25 2.25 0 01-2.25 2.25H6.75a2.25 2.25 0 01-2.25-2.25v-7.5A2.25 2.25 0 016.75 6zM9 12h.008v.008H9V12zm6 0h.008v.008H15V12zM9.75 15.75h4.5" /></svg>,
    activeIcon: <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M11.25 3a.75.75 0 011.5 0v.836a.75.75 0 01-.375.113h-.75A.75.75 0 0111.25 3.836V3z" /><path fillRule="evenodd" d="M6.75 6A2.25 2.25 0 004.5 8.25v7.5A2.25 2.25 0 006.75 18h10.5a2.25 2.25 0 002.25-2.25v-7.5A2.25 2.25 0 0017.25 6H6.75zM9 10.5a1.125 1.125 0 100 2.25 1.125 1.125 0 000-2.25zm6 0a1.125 1.125 0 100 2.25 1.125 1.125 0 000-2.25zm-5.25 4.5a.75.75 0 000 1.5h4.5a.75.75 0 000-1.5h-4.5z" clipRule="evenodd" /></svg>,
  },
  {
    href: '/coach',
    labelKey: 'coach',
    shortcut: 'C',
    icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" /></svg>,
    activeIcon: <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path fillRule="evenodd" d="M9 4.5a.75.75 0 01.721.544l.813 2.846a3.75 3.75 0 002.576 2.576l2.846.813a.75.75 0 010 1.442l-2.846.813a3.75 3.75 0 00-2.576 2.576l-.813 2.846a.75.75 0 01-1.442 0l-.813-2.846a3.75 3.75 0 00-2.576-2.576l-2.846-.813a.75.75 0 010-1.442l2.846-.813A3.75 3.75 0 007.466 7.89l.813-2.846A.75.75 0 019 4.5zM18 1.5a.75.75 0 01.728.568l.258 1.036c.236.94.97 1.674 1.91 1.91l1.036.258a.75.75 0 010 1.456l-1.036.258c-.94.236-1.674.97-1.91 1.91l-.258 1.036a.75.75 0 01-1.456 0l-.258-1.036a2.625 2.625 0 00-1.91-1.91l-1.036-.258a.75.75 0 010-1.456l1.036-.258a2.625 2.625 0 001.91-1.91l.258-1.036A.75.75 0 0118 1.5zM16.5 15a.75.75 0 01.712.513l.394 1.183c.15.452.6.832 1.057.982l1.183.394a.75.75 0 010 1.428l-1.183.394c-.456.15-.907.53-1.057.982l-.394 1.183a.75.75 0 01-1.424 0l-.394-1.183a1.5 1.5 0 00-1.057-.982l-1.183-.394a.75.75 0 010-1.428l1.183-.394a1.5 1.5 0 001.057-.982l.394-1.183A.75.75 0 0116.5 15z" clipRule="evenodd" /></svg>,
  },
  {
    href: '/database',
    labelKey: 'database',
    shortcut: 'O',
    icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>,
    activeIcon: <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M11.25 4.533A9.707 9.707 0 006 3a9.735 9.735 0 00-3.25.555.75.75 0 00-.5.707v14.25a.75.75 0 001 .707A8.237 8.237 0 016 18.75c1.995 0 3.823.707 5.25 1.886V4.533zM12.75 20.636A8.214 8.214 0 0118 18.75c.966 0 1.89.166 2.75.47a.75.75 0 001-.708V4.262a.75.75 0 00-.5-.707A9.735 9.735 0 0018 3a9.707 9.707 0 00-5.25 1.533v16.103z" /></svg>,
  },
  {
    href: '/puzzle',
    labelKey: 'puzzles',
    shortcut: 'P',
    icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M14.25 6.087c0-.355.186-.676.401-.959.221-.29.349-.634.349-1.003 0-1.036-1.007-1.875-2.25-1.875s-2.25.84-2.25 1.875c0 .369.128.713.349 1.003.215.283.401.604.401.959v0a.64.64 0 01-.657.643 48.39 48.39 0 01-4.163-.3c.186 1.613.293 3.25.315 4.907a.656.656 0 01-.658.663v0c-.355 0-.676-.186-.959-.401a1.647 1.647 0 00-1.003-.349c-1.036 0-1.875 1.007-1.875 2.25s.84 2.25 1.875 2.25c.369 0 .713-.128 1.003-.349.283-.215.604-.401.959-.401v0c.31 0 .555.26.532.57a48.039 48.039 0 01-.642 5.056c1.518.19 3.058.309 4.616.354a.64.64 0 00.657-.643v0c0-.355-.186-.676-.401-.959a1.647 1.647 0 01-.349-1.003c0-1.035 1.008-1.875 2.25-1.875 1.243 0 2.25.84 2.25 1.875 0 .369-.128.713-.349 1.003-.215.283-.4.604-.4.959v0c0 .333.277.599.61.58a48.1 48.1 0 005.427-.63 48.05 48.05 0 00.582-4.717.532.532 0 00-.533-.57v0c-.355 0-.676.186-.959.401-.29.221-.634.349-1.003.349-1.035 0-1.875-1.007-1.875-2.25s.84-2.25 1.875-2.25c.37 0 .713.128 1.003.349.283.215.604.401.96.401v0a.656.656 0 00.658-.663 48.422 48.422 0 00-.37-5.36c-1.886.342-3.81.574-5.766.689a.578.578 0 01-.61-.58v0z" /></svg>,
    activeIcon: <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M14.25 6.087c0-.355.186-.676.401-.959.221-.29.349-.634.349-1.003 0-1.036-1.007-1.875-2.25-1.875s-2.25.84-2.25 1.875c0 .369.128.713.349 1.003.215.283.401.604.401.959v0a.64.64 0 01-.657.643 48.39 48.39 0 01-4.163-.3c.186 1.613.293 3.25.315 4.907a.656.656 0 01-.658.663v0c-.355 0-.676-.186-.959-.401a1.647 1.647 0 00-1.003-.349c-1.036 0-1.875 1.007-1.875 2.25s.84 2.25 1.875 2.25c.369 0 .713-.128 1.003-.349.283-.215.604-.401.959-.401v0c.31 0 .555.26.532.57a48.039 48.039 0 01-.642 5.056c1.518.19 3.058.309 4.616.354a.64.64 0 00.657-.643v0c0-.355-.186-.676-.401-.959a1.647 1.647 0 01-.349-1.003c0-1.035 1.008-1.875 2.25-1.875 1.243 0 2.25.84 2.25 1.875 0 .369-.128.713-.349 1.003-.215.283-.4.604-.4.959v0c0 .333.277.599.61.58a48.1 48.1 0 005.427-.63 48.05 48.05 0 00.582-4.717.532.532 0 00-.533-.57v0c-.355 0-.676.186-.959.401-.29.221-.634.349-1.003.349-1.035 0-1.875-1.007-1.875-2.25s.84-2.25 1.875-2.25c.37 0 .713.128 1.003.349.283.215.604.401.96.401v0a.656.656 0 00.658-.663 48.422 48.422 0 00-.37-5.36c-1.886.342-3.81.574-5.766.689a.578.578 0 01-.61-.58v0z" /></svg>,
  },
  {
    href: '/editor',
    labelKey: 'editor',
    shortcut: 'E',
    icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" /></svg>,
    activeIcon: <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M21.731 2.269a2.625 2.625 0 00-3.712 0l-1.157 1.157 3.712 3.712 1.157-1.157a2.625 2.625 0 000-3.712zM19.513 8.199l-3.712-3.712-12.15 12.15a5.25 5.25 0 00-1.32 2.214l-.8 2.685a.75.75 0 00.933.933l2.685-.8a5.25 5.25 0 002.214-1.32L19.513 8.2z" /></svg>,
  },
];

const bottomItems: SidebarItem[] = [
  {
    href: '/settings',
    labelKey: 'settings',
    icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" /><path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>,
    activeIcon: <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path fillRule="evenodd" d="M11.078 2.25c-.917 0-1.699.663-1.85 1.567L9.05 4.889c-.02.12-.115.26-.297.348a7.03 7.03 0 00-.573.332c-.17.108-.353.14-.502.088l-1.08-.405a1.875 1.875 0 00-2.282.819l-.922 1.597a1.875 1.875 0 00.432 2.385l.84.692c.095.078.17.229.154.43a7.598 7.598 0 000 .664c.016.201-.059.352-.153.43l-.841.692a1.875 1.875 0 00-.432 2.385l.922 1.597a1.875 1.875 0 002.282.818l1.019-.382c.15-.053.334-.022.503.087.17.11.34.228.573.332.182.088.277.228.297.35l.178 1.07c.151.904.933 1.567 1.85 1.567h1.844c.916 0 1.699-.663 1.85-1.567l.178-1.072c.02-.12.114-.26.297-.349.232-.104.4-.222.573-.332.17-.108.352-.14.5-.088l1.08.405a1.875 1.875 0 002.282-.819l.923-1.597a1.875 1.875 0 00-.432-2.385l-.84-.692c-.095-.078-.17-.229-.154-.43a7.614 7.614 0 000-.664c-.016-.201.059-.352.153-.43l.84-.692c.708-.582.891-1.59.433-2.385l-.922-1.597a1.875 1.875 0 00-2.282-.818l-1.02.382c-.15.053-.333.022-.502-.087a7.036 7.036 0 00-.573-.332c-.183-.088-.277-.228-.297-.35l-.179-1.07a1.875 1.875 0 00-1.85-1.567h-1.843zM12 15.75a3.75 3.75 0 100-7.5 3.75 3.75 0 000 7.5z" clipRule="evenodd" /></svg>,
  },
  {
    href: '/profile',
    labelKey: 'profile',
    icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" /></svg>,
    activeIcon: <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path fillRule="evenodd" d="M7.5 6a4.5 4.5 0 119 0 4.5 4.5 0 01-9 0zM3.751 20.105a8.25 8.25 0 0116.498 0 .75.75 0 01-.437.695A18.683 18.683 0 0112 22.5c-2.786 0-5.433-.608-7.812-1.7a.75.75 0 01-.437-.695z" clipRule="evenodd" /></svg>,
  },
];

export default function DesktopSidebar() {
  const pathname = usePathname();
  const t = useTranslations('navigation');
  const locale = useLocale();
  const [collapsed, setCollapsed] = useLocalStorage('sidebar_collapsed', false);
  const { isSignedIn } = useAuth();
  const branding = useBranding();
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  const isActive = (href: string) => {
    if (!pathname) return false;
    if (href === '/dashboard') return pathname === '/' || pathname === '/dashboard';
    return pathname.startsWith(href);
  };

  const renderItem = (item: SidebarItem) => {
    const active = isActive(item.href);
    return (
      <PrefetchLink
        key={item.href}
        href={item.href}
        onWarmup={item.href === '/play' ? warmMaia : undefined}
        onTouchStart={item.href === '/play' ? warmMaia : undefined}
        title={collapsed ? `${t(item.labelKey)} (${item.shortcut || ''})` : undefined}
        className={`flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-150 group relative ${
          active
            ? 'bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 font-semibold'
            : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-white/5 hover:text-gray-900 dark:hover:text-gray-200'
        } ${collapsed ? 'justify-center' : ''}`}
      >
        {active && (
          <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-6 bg-purple-600 dark:bg-purple-400 rounded-r-full" />
        )}
        <div className="flex-shrink-0">
          {active ? item.activeIcon : item.icon}
        </div>
        {!collapsed && (
          <span className="text-sm truncate">{t(item.labelKey)}</span>
        )}
        {!collapsed && item.shortcut && (
          <kbd className="ml-auto text-[10px] text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-white/10 px-1.5 py-0.5 rounded font-mono opacity-0 group-hover:opacity-100 transition-opacity">
            {item.shortcut}
          </kbd>
        )}
      </PrefetchLink>
    );
  };

  return (
    <aside
      className={`sticky top-0 h-screen bg-white dark:bg-[#141414] border-r border-gray-200 dark:border-[#2a2a2a] flex flex-col transition-all duration-200 overflow-visible ${
        collapsed ? 'w-[64px]' : 'w-[220px]'
      }`}
    >
      {/* Logo */}
      <div className={`h-16 flex items-center border-b border-gray-100 dark:border-[#2a2a2a] px-3 ${collapsed ? 'justify-center' : 'gap-2'}`}>
        {branding.logoUrl ? (
          // Tenant logos live on Supabase Storage which isn't in next.config images.remotePatterns,
          // so use a plain <img> instead of next/image.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={branding.logoUrl}
            alt={branding.name}
            width={40}
            height={40}
            className="h-10 w-10 rounded object-contain"
          />
        ) : (
          <Image
            src="/static/images/chesster-logo-v3.png"
            alt={branding.name}
            width={28}
            height={28}
          />
        )}
        {!collapsed && (
          <span className="font-bold text-gray-900 dark:text-gray-100 text-lg truncate">
            {branding.name}
          </span>
        )}
      </div>

      {/* Main nav */}
      <nav className="flex-1 px-2 py-3 space-y-1 overflow-y-auto">
        {items.map(renderItem)}
      </nav>

      {/* Separator */}
      <div className="border-t border-gray-100 dark:border-[#2a2a2a] mx-3" />

      {/* Bottom items */}
      <div className="px-2 py-2 space-y-1">
        {bottomItems.map(renderItem)}
      </div>

      {/* Language + User */}
      <div className={`px-3 py-3 border-t border-gray-100 dark:border-[#2a2a2a] flex items-center ${collapsed ? 'justify-center' : 'gap-3'}`}>
        {!collapsed && <LanguageSwitcher currentLocale={locale} variant="minimal" dropUp />}
        {mounted && isSignedIn && (
          <UserButton
            appearance={{
              elements: {
                avatarBox: "w-8 h-8"
              }
            }}
          />
        )}
      </div>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3 top-20 w-6 h-6 bg-white dark:bg-[#1a1a1a] border border-gray-200 dark:border-[#2a2a2a] rounded-full shadow-sm flex items-center justify-center text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:shadow-md transition-all z-30"
      >
        <svg className={`w-3 h-3 transition-transform ${collapsed ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
      </button>
    </aside>
  );
}
