'use client';

import { ReactNode, useState } from 'react';
import { useBranding, useOrganization } from '@/contexts/OrganizationContext';
import AdminSidebar from './AdminSidebar';
import { IntercomWidget } from '@/components/support/IntercomWidget';

type MemberRole = 'owner' | 'admin' | 'teacher' | 'student';

interface Props {
  role: MemberRole;
  children: ReactNode;
  plan?: string | null;
  userId?: string | null;
  userEmail?: string | null;
  userName?: string | null;
}

export default function AdminShell({
  role,
  children,
  plan,
  userId,
  userEmail,
  userName,
}: Props) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const branding = useBranding();
  const { org } = useOrganization();

  return (
    <div className="flex min-h-screen bg-gray-50 dark:bg-gray-900">
      <AdminSidebar
        currentRole={role}
        mobileOpen={mobileOpen}
        onClose={() => setMobileOpen(false)}
      />
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="md:hidden flex items-center gap-3 px-4 py-3 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
            aria-expanded={mobileOpen}
            className="h-11 w-11 -ml-2 inline-flex items-center justify-center rounded-lg text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke="currentColor"
              className="h-6 w-6"
              aria-hidden="true"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5M3.75 17.25h16.5" />
            </svg>
          </button>
          <span className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
            {branding.name}
          </span>
        </header>
        <main className="flex-1 min-w-0 p-4 sm:p-6 md:p-8">{children}</main>
      </div>
      <IntercomWidget
        tier={plan}
        userId={userId ?? undefined}
        email={userEmail ?? undefined}
        name={userName ?? undefined}
        orgId={org?.id ?? null}
        orgName={org?.name ?? null}
      />
    </div>
  );
}
