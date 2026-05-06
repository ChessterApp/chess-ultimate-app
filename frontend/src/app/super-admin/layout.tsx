import { auth, currentUser } from '@clerk/nextjs/server';
import { headers } from 'next/headers';
import { redirect } from 'next/navigation';
import { ReactNode } from 'react';
import SuperAdminSidebar from './SuperAdminSidebar';

export const dynamic = 'force-dynamic';

function isApexHost(host: string | null): boolean {
  if (!host) return false;
  const bare = host.split(':')[0];
  if (bare === 'chesster.io' || bare === 'www.chesster.io') return true;
  if (bare === 'localhost' || bare === '127.0.0.1' || bare.startsWith('localhost')) return true;
  return false;
}

export default async function SuperAdminLayout({ children }: { children: ReactNode }) {
  // Apex-only — middleware redirects subdomains, but we double-check at layout time
  // to defend against any rewrite/proxy that might bypass the edge.
  const headersList = await headers();
  if (!isApexHost(headersList.get('host'))) {
    redirect('https://chesster.io/super-admin');
  }

  const { userId } = await auth();
  if (!userId) {
    redirect('/sign-in?redirect_url=/super-admin');
  }

  const user = await currentUser();
  const role = (user?.publicMetadata as Record<string, unknown> | null)?.platform_role;
  const twoFactor = user?.twoFactorEnabled === true;

  if (role !== 'super_admin') {
    redirect('/dashboard');
  }
  if (!twoFactor) {
    redirect('/account/security?reason=2fa-required');
  }

  return (
    <div className="flex min-h-screen bg-gray-50 dark:bg-gray-900">
      <SuperAdminSidebar />
      <main className="flex-1 min-w-0 p-6 md:p-8">{children}</main>
    </div>
  );
}
