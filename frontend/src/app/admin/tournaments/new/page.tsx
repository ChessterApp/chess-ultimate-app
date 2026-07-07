'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useOrganization } from '@/contexts/OrganizationContext';

interface TournamentForm {
  name: string;
  description: string;
  location: string;
  city: string;
  country: string;
  start_date: string;
  end_date: string;
  registration_deadline: string;
  time_control: string;
  format: string;
  max_participants: string;
  entry_fee: string;
  currency: string;
  prize_fund: string;
  rating_category: string;
  min_rating: string;
  max_rating: string;
  is_rated: boolean;
  tournament_mode: 'offline' | 'online';
}

const INITIAL_FORM: TournamentForm = {
  name: '',
  description: '',
  location: '',
  city: '',
  country: 'KZ',
  start_date: '',
  end_date: '',
  registration_deadline: '',
  time_control: '',
  format: 'swiss',
  max_participants: '',
  entry_fee: '0',
  currency: 'KZT',
  prize_fund: '',
  rating_category: '',
  min_rating: '',
  max_rating: '',
  is_rated: false,
  tournament_mode: 'offline',
};

export default function AdminNewTournamentPage() {
  const router = useRouter();
  const { org } = useOrganization();
  const [form, setForm] = useState<TournamentForm>(INITIAL_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  function updateField(field: keyof TournamentForm, value: string | boolean) {
    setForm(prev => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!org?.id) return;
    setSaving(true);
    setError('');

    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || '';
      const body: Record<string, unknown> = {
        ...form,
        organizer_org_id: org.id,
        max_participants: form.max_participants ? parseInt(form.max_participants) : null,
        entry_fee: parseFloat(form.entry_fee) || 0,
        prize_fund: form.prize_fund ? parseFloat(form.prize_fund) : null,
        min_rating: form.min_rating ? parseInt(form.min_rating) : null,
        max_rating: form.max_rating ? parseInt(form.max_rating) : null,
      };

      const res = await fetch(`${backendUrl}/api/tournaments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (res.ok) {
        router.push('/admin/tournaments');
      } else {
        const data = await res.json();
        setError(data.error || 'Failed to create tournament');
      }
    } catch {
      setError('Network error. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">
        Create Tournament
      </h1>

      <form onSubmit={handleSubmit} className="space-y-6 max-w-2xl">
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 dark:bg-red-900/20 dark:border-red-800 p-3 text-sm text-red-700 dark:text-red-300">
            {error}
          </div>
        )}

        {/* Basic Info */}
        <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Basic Information</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name *</label>
              <input
                type="text"
                value={form.name}
                onChange={e => updateField('name', e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Description</label>
              <textarea
                value={form.description}
                onChange={e => updateField('description', e.target.value)}
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Format</label>
                <select
                  value={form.format}
                  onChange={e => updateField('format', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                >
                  <option value="swiss">Swiss</option>
                  <option value="round_robin">Round Robin</option>
                  <option value="elimination">Elimination</option>
                  <option value="team">Team</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Time Control *</label>
                <input
                  type="text"
                  value={form.time_control}
                  onChange={e => updateField('time_control', e.target.value)}
                  placeholder="e.g. 90+30"
                  required
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                />
              </div>
            </div>
          </div>
        </section>

        {/* Location & Dates */}
        <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Location & Dates</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Venue *</label>
              <input
                type="text"
                value={form.location}
                onChange={e => updateField('location', e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">City</label>
                <input
                  type="text"
                  value={form.city}
                  onChange={e => updateField('city', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Country</label>
                <input
                  type="text"
                  value={form.country}
                  onChange={e => updateField('country', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                />
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Start Date *</label>
                <input
                  type="date"
                  value={form.start_date}
                  onChange={e => updateField('start_date', e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">End Date *</label>
                <input
                  type="date"
                  value={form.end_date}
                  onChange={e => updateField('end_date', e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Reg. Deadline *</label>
                <input
                  type="date"
                  value={form.registration_deadline}
                  onChange={e => updateField('registration_deadline', e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                />
              </div>
            </div>
          </div>
        </section>

        {/* Registration & Fees */}
        <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Registration & Fees</h2>
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Max Participants</label>
                <input
                  type="number"
                  value={form.max_participants}
                  onChange={e => updateField('max_participants', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Entry Fee</label>
                <input
                  type="number"
                  step="0.01"
                  value={form.entry_fee}
                  onChange={e => updateField('entry_fee', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Currency</label>
                <select
                  value={form.currency}
                  onChange={e => updateField('currency', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                >
                  <option value="KZT">KZT</option>
                  <option value="USD">USD</option>
                  <option value="EUR">EUR</option>
                </select>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Prize Fund</label>
              <input
                type="number"
                step="0.01"
                value={form.prize_fund}
                onChange={e => updateField('prize_fund', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
              />
            </div>
          </div>
        </section>

        {/* Rating Restrictions */}
        <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Rating Restrictions</h2>
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Category</label>
                <select
                  value={form.rating_category}
                  onChange={e => updateField('rating_category', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                >
                  <option value="">Open</option>
                  <option value="C">C (&lt;1400)</option>
                  <option value="B">B (1400-1799)</option>
                  <option value="A">A (1800-2199)</option>
                  <option value="Master">Master (2200+)</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Min Rating</label>
                <input
                  type="number"
                  value={form.min_rating}
                  onChange={e => updateField('min_rating', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Max Rating</label>
                <input
                  type="number"
                  value={form.max_rating}
                  onChange={e => updateField('max_rating', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                />
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Tournament Mode</label>
                <select
                  value={form.tournament_mode}
                  onChange={e => updateField('tournament_mode', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                >
                  <option value="offline">Offline (OTB)</option>
                  <option value="online">Online</option>
                </select>
              </div>
              <label className="flex items-center gap-2 pt-6">
                <input
                  type="checkbox"
                  checked={form.is_rated}
                  onChange={e => updateField('is_rated', e.target.checked)}
                  className="rounded border-gray-300 dark:border-gray-600"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">
                  Rated (updates Local App Rating; only applied when mode is offline)
                </span>
              </label>
            </div>
          </div>
        </section>

        {/* Submit */}
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={saving}
            className="px-6 py-2 text-sm font-medium text-white rounded-lg disabled:opacity-50 transition-colors"
            style={{ backgroundColor: 'var(--brand-primary)' }}
          >
            {saving ? 'Creating...' : 'Create Tournament'}
          </button>
          <button
            type="button"
            onClick={() => router.push('/admin/tournaments')}
            className="px-6 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
