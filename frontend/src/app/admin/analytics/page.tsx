'use client';

import { useEffect, useState } from 'react';
import { useOrganization } from '@/contexts/OrganizationContext';

interface AnalyticsData {
  totalStudents: number;
  activeThisWeek: number;
  activeThisMonth: number;
  completionRate: number;
  averageSessionMinutes: number;
  weeklyActive: number[];
}

function StatCard({ label, value, suffix }: { label: string; value: number | string; suffix?: string }) {
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6">
      <p className="text-sm text-gray-500 dark:text-gray-400">{label}</p>
      <p className="mt-2 text-3xl font-semibold text-gray-900 dark:text-gray-100">
        {value}{suffix}
      </p>
    </div>
  );
}

function SimpleBarChart({ data, labels }: { data: number[]; labels: string[] }) {
  const max = Math.max(...data, 1);
  return (
    <div className="flex items-end gap-2 h-40">
      {data.map((value, i) => (
        <div key={i} className="flex-1 flex flex-col items-center gap-1">
          <span className="text-xs text-gray-500 dark:text-gray-400">{value}</span>
          <div
            className="w-full rounded-t"
            style={{
              height: `${(value / max) * 100}%`,
              minHeight: value > 0 ? 4 : 0,
              backgroundColor: 'var(--brand-primary)',
            }}
          />
          <span className="text-xs text-gray-500 dark:text-gray-400">{labels[i]}</span>
        </div>
      ))}
    </div>
  );
}

export default function AdminAnalyticsPage() {
  const { org } = useOrganization();
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!org?.id) return;
    fetchAnalytics();
  }, [org?.id]);

  async function fetchAnalytics() {
    if (!org?.id) return;
    setLoading(true);
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || '';
      const res = await fetch(`${backendUrl}/api/admin/organizations/${org.id}/stats`);
      if (res.ok) {
        const stats = await res.json();
        setData({
          totalStudents: stats.student_count || 0,
          activeThisWeek: stats.active_this_week || 0,
          activeThisMonth: stats.active_this_month || 0,
          completionRate: stats.course_completion_rate || 0,
          averageSessionMinutes: stats.avg_session_minutes || 0,
          weeklyActive: stats.weekly_active || [0, 0, 0, 0],
        });
      } else {
        // Use placeholder data if API not available
        setData({
          totalStudents: 0,
          activeThisWeek: 0,
          activeThisMonth: 0,
          completionRate: 0,
          averageSessionMinutes: 0,
          weeklyActive: [0, 0, 0, 0],
        });
      }
    } catch {
      setData({
        totalStudents: 0,
        activeThisWeek: 0,
        activeThisMonth: 0,
        completionRate: 0,
        averageSessionMinutes: 0,
        weeklyActive: [0, 0, 0, 0],
      });
    } finally {
      setLoading(false);
    }
  }

  const weekLabels = ['Week 1', 'Week 2', 'Week 3', 'Week 4'];

  if (loading) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">Analytics</h1>
        <p className="text-gray-500 dark:text-gray-400">Loading...</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">Analytics</h1>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
        <StatCard label="Total Students" value={data?.totalStudents ?? 0} />
        <StatCard label="Active This Week" value={data?.activeThisWeek ?? 0} />
        <StatCard label="Active This Month" value={data?.activeThisMonth ?? 0} />
        <StatCard label="Course Completion" value={data?.completionRate ?? 0} suffix="%" />
      </div>

      {/* Activity Chart */}
      <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Weekly Active Users</h2>
        <SimpleBarChart data={data?.weeklyActive ?? []} labels={weekLabels} />
      </section>

      {/* Session Stats */}
      <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Engagement</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Avg. Session Duration</p>
            <p className="mt-1 text-2xl font-semibold text-gray-900 dark:text-gray-100">
              {data?.averageSessionMinutes ?? 0} min
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Retention Rate</p>
            <p className="mt-1 text-2xl font-semibold text-gray-900 dark:text-gray-100">
              {data?.totalStudents ? Math.round((data.activeThisMonth / data.totalStudents) * 100) : 0}%
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
