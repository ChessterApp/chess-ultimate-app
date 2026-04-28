'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useOrganization } from '@/contexts/OrganizationContext';

interface Tournament {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
  city: string | null;
  country: string | null;
  status: string;
  format: string | null;
  entry_fee: number;
  currency: string;
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    upcoming: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
    registration_open: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
    in_progress: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300',
    completed: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
    cancelled: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  };

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors[status] || colors.upcoming}`}>
      {status.replace('_', ' ')}
    </span>
  );
}

export default function AdminTournamentsPage() {
  const { org } = useOrganization();
  const [tournaments, setTournaments] = useState<Tournament[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!org?.id) return;
    fetchTournaments();
  }, [org?.id]);

  async function fetchTournaments() {
    if (!org?.id) return;
    setLoading(true);
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || '';
      const res = await fetch(`${backendUrl}/api/tournaments?org_id=${org.id}`);
      if (res.ok) {
        const data = await res.json();
        setTournaments(data.tournaments || []);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Tournaments</h1>
        <Link
          href="/admin/tournaments/new"
          className="px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors"
          style={{ backgroundColor: 'var(--brand-primary)' }}
        >
          Create Tournament
        </Link>
      </div>

      <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Name</th>
              <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Dates</th>
              <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Location</th>
              <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Status</th>
              <th className="text-right px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-500">Loading...</td>
              </tr>
            ) : tournaments.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-500">
                  No tournaments yet. Create your first tournament to get started.
                </td>
              </tr>
            ) : (
              tournaments.map(t => (
                <tr key={t.id} className="border-b border-gray-100 dark:border-gray-700 last:border-0">
                  <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">{t.name}</td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                    {new Date(t.start_date).toLocaleDateString()} — {new Date(t.end_date).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                    {[t.city, t.country].filter(Boolean).join(', ') || '—'}
                  </td>
                  <td className="px-4 py-3"><StatusBadge status={t.status} /></td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Link href={`/admin/tournaments/${t.id}/edit`} className="text-xs text-blue-600 hover:text-blue-800 dark:text-blue-400">
                        Edit
                      </Link>
                      <Link href={`/admin/tournaments/${t.id}/pairings`} className="text-xs text-blue-600 hover:text-blue-800 dark:text-blue-400">
                        Pairings
                      </Link>
                      <Link href={`/admin/tournaments/${t.id}/results`} className="text-xs text-blue-600 hover:text-blue-800 dark:text-blue-400">
                        Results
                      </Link>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
