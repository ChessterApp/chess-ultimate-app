'use client';

import { useEffect, useState } from 'react';
import { useOrganization } from '@/contexts/OrganizationContext';

/**
 * Branches admin page (PRD §11.3 #2).
 *
 * Owner/admin can create branches and assign members. Branch admins land
 * here too but see only their own branch (server-side scoping).
 */

interface Branch {
  id: string;
  name: string;
  slug: string;
  address?: string | null;
}

export default function BranchesAdminPage() {
  const { org } = useOrganization();
  const orgId = org?.id || '';
  const [branches, setBranches] = useState<Branch[]>([]);
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    if (!orgId) return;
    try {
      const res = await fetch(`/api/admin/organizations/${orgId}/branches`);
      if (!res.ok) {
        setError(`Failed to load (${res.status})`);
        return;
      }
      const body = await res.json();
      setBranches(body.branches || []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'load failed');
    }
  }

  useEffect(() => {
    refresh();
  }, [orgId]);

  async function create() {
    if (!orgId || !name || !slug) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/admin/organizations/${orgId}/branches`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, slug }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.message || `Failed (${res.status})`);
        return;
      }
      setName('');
      setSlug('');
      refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Branches</h1>
        <p className="text-sm text-gray-500">
          Multi-location schools — assign coaches and students to a branch.
        </p>
      </header>

      <section className="rounded-lg border border-gray-200 p-4 space-y-2">
        <h2 className="font-semibold">Add a branch</h2>
        <div className="grid grid-cols-2 gap-2">
          <input
            placeholder="Almaty Downtown"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="rounded border border-gray-300 px-3 py-2"
          />
          <input
            placeholder="almaty-downtown"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            className="rounded border border-gray-300 px-3 py-2"
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="button"
          onClick={create}
          disabled={busy || !name || !slug}
          className="rounded bg-blue-600 px-4 py-2 text-white font-semibold disabled:opacity-50"
        >
          Create branch
        </button>
      </section>

      <section>
        <h2 className="font-semibold mb-2">Existing branches</h2>
        {branches.length === 0 ? (
          <p className="text-sm text-gray-500">No branches yet.</p>
        ) : (
          <ul className="divide-y divide-gray-100 border border-gray-200 rounded">
            {branches.map((b) => (
              <li key={b.id} className="p-3">
                <div className="font-medium">{b.name}</div>
                <div className="text-xs text-gray-500">{b.slug}</div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
