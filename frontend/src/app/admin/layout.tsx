import { auth } from '@clerk/nextjs/server';
import { headers } from 'next/headers';
import { redirect } from 'next/navigation';
import { ReactNode } from 'react';
import AdminSidebar from './AdminSidebar';

type MemberRole = 'owner' | 'admin' | 'teacher' | 'student';
const ADMIN_ROLES: MemberRole[] = ['owner', 'admin', 'teacher'];

async function getUserOrgRole(userId: string, orgId: string): Promise<MemberRole | null> {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001';
    const res = await fetch(
      `${backendUrl}/api/admin/organizations/${orgId}/members?user_id=${userId}`,
      { signal: AbortSignal.timeout(5000), cache: 'no-store' }
    );
    if (!res.ok) return null;
    const data = await res.json();
    const member = data.members?.find((m: { user_id: string }) => m.user_id === userId);
    return member?.role || null;
  } catch {
    return null;
  }
}

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const { userId } = await auth();
  if (!userId) {
    redirect('/sign-in');
  }

  const headersList = await headers();
  const orgId = headersList.get('x-org-id');

  if (!orgId) {
    redirect('/dashboard');
  }

  const role = await getUserOrgRole(userId, orgId);
  if (!role || !ADMIN_ROLES.includes(role)) {
    redirect('/dashboard');
  }

  return (
    <div className="flex min-h-screen bg-gray-50 dark:bg-gray-900">
      <AdminSidebar currentRole={role} />
      <main className="flex-1 min-w-0 p-6 md:p-8">
        {children}
      </main>
    </div>
  );
}
