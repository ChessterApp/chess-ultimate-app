import { auth } from '@clerk/nextjs/server';
import { headers } from 'next/headers';
import { redirect } from 'next/navigation';
import { ReactNode } from 'react';
import AdminShell from './AdminShell';

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

const APEX_HOST = 'chesster.io';

function isApexHost(host: string): boolean {
  const bare = host.split(':')[0];
  return bare === APEX_HOST || bare === `www.${APEX_HOST}` || bare === 'localhost' || bare === '127.0.0.1';
}

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const headersList = await headers();
  const host = headersList.get('host') || APEX_HOST;
  const pathname = headersList.get('x-pathname') || '/admin';

  const { userId } = await auth();
  if (!userId) {
    if (isApexHost(host)) {
      redirect('/sign-in');
    }
    // Subdomain: Clerk's sign-in is only registered on the apex, so send the
    // user there and bounce back to the originating tenant URL post-auth.
    const returnUrl = `https://${host}${pathname}`;
    redirect(`https://${APEX_HOST}/sign-in?redirect_url=${encodeURIComponent(returnUrl)}`);
  }

  const orgId = headersList.get('x-org-id');

  if (!orgId) {
    redirect('/dashboard');
  }

  const role = await getUserOrgRole(userId, orgId);
  if (!role || !ADMIN_ROLES.includes(role)) {
    redirect('/dashboard');
  }

  // PRD §11.3 #5 — Intercom widget gated by plan. Best-effort fetch of the
  // billing plan; intercom widget no-ops on starter or missing plan.
  const plan = await getOrgPlan(orgId);

  return (
    <AdminShell role={role} plan={plan} userId={userId}>
      {children}
    </AdminShell>
  );
}

async function getOrgPlan(orgId: string): Promise<string | null> {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001';
    const res = await fetch(`${backendUrl}/api/admin/organizations/${orgId}/checklist`, {
      signal: AbortSignal.timeout(3000),
      cache: 'no-store',
    });
    if (!res.ok) return null;
    const body = await res.json();
    return body?.org?.plan ?? null;
  } catch {
    return null;
  }
}
