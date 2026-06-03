import { headers } from 'next/headers';
import { OnboardingChecklist } from '@/components/admin/OnboardingChecklist';
import { LoomEmbed } from '@/components/support/LoomEmbed';
import { buildLoomConfig, pickLoomForTier } from '@/lib/loom';

interface OrgStats {
  student_count: number;
  active_this_week: number;
  course_completion_rate: number;
}

interface OrgChecklistSnapshot {
  org: {
    logoUrl?: string | null;
    primaryColor?: string | null;
    secondaryColor?: string | null;
    accentColor?: string | null;
    customDomainStatus?: string | null;
    emailSenderStatus?: string | null;
    landingPageConfig?: Record<string, unknown> | null;
    createdAt?: string | null;
    plan?: string | null;
  };
  studentCount: number;
  teacherCount: number;
}

async function fetchChecklistSnapshot(orgId: string): Promise<OrgChecklistSnapshot | null> {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001';
    const res = await fetch(`${backendUrl}/api/admin/organizations/${orgId}/checklist`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) return null;
    return (await res.json()) as OrgChecklistSnapshot;
  } catch {
    return null;
  }
}

async function fetchOrgStats(orgId: string): Promise<OrgStats> {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001';
    const res = await fetch(`${backendUrl}/api/admin/organizations/${orgId}/stats`, {
      signal: AbortSignal.timeout(5000),
      cache: 'no-store',
    });
    if (!res.ok) throw new Error('Failed to fetch stats');
    return await res.json();
  } catch {
    return { student_count: 0, active_this_week: 0, course_completion_rate: 0 };
  }
}

function StatCard({ label, value, suffix }: { label: string; value: number; suffix?: string }) {
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6">
      <p className="text-sm text-gray-500 dark:text-gray-400">{label}</p>
      <p className="mt-2 text-3xl font-semibold text-gray-900 dark:text-gray-100">
        {value}{suffix}
      </p>
    </div>
  );
}

export default async function AdminDashboardPage() {
  const headersList = await headers();
  const orgId = headersList.get('x-org-id') || '';
  const [stats, checklist] = await Promise.all([
    fetchOrgStats(orgId),
    orgId ? fetchChecklistSnapshot(orgId) : Promise.resolve(null),
  ]);

  // PRD §11.3 #5: Loom embed in the post-onboarding checklist for
  // directors who didn't watch the Loom in the activation screen.
  const loomCfg = buildLoomConfig(process.env as Record<string, string | undefined>);
  const loomUrl = pickLoomForTier(loomCfg, checklist?.org?.plan ?? null);

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">
        Dashboard
      </h1>
      {checklist && <OnboardingChecklist snapshot={checklist} />}
      {loomUrl && (
        <div className="mb-6">
          <LoomEmbed
            url={loomUrl}
            title="Welcome — 2-minute walkthrough"
          />
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        <StatCard label="Total Students" value={stats.student_count} />
        <StatCard label="Active This Week" value={stats.active_this_week} />
        <StatCard label="Course Completion" value={stats.course_completion_rate} suffix="%" />
      </div>
    </div>
  );
}
