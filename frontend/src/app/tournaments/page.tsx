'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';

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
  };

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors[status] || colors.upcoming}`}>
      {status.replace('_', ' ')}
    </span>
  );
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function CalendarView({ tournaments, year, month }: { tournaments: Tournament[]; year: number; month: number }) {
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: (number | null)[] = [];

  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  function tournamentsOnDay(day: number): Tournament[] {
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    return tournaments.filter(t => {
      const start = t.start_date.split('T')[0];
      const end = t.end_date.split('T')[0];
      return start <= dateStr && end >= dateStr;
    });
  }

  return (
    <div>
      <div className="grid grid-cols-7 gap-px bg-gray-200 dark:bg-gray-700 rounded-xl overflow-hidden border border-gray-200 dark:border-gray-700">
        {DAYS.map(day => (
          <div key={day} className="bg-gray-50 dark:bg-gray-800 px-2 py-2 text-xs font-medium text-gray-500 dark:text-gray-400 text-center">
            {day}
          </div>
        ))}
        {cells.map((day, i) => {
          const dayTournaments = day ? tournamentsOnDay(day) : [];
          return (
            <div
              key={i}
              className={`bg-white dark:bg-gray-800 min-h-[80px] p-1 ${day ? '' : 'bg-gray-50 dark:bg-gray-900'}`}
            >
              {day && (
                <>
                  <span className="text-xs text-gray-500 dark:text-gray-400">{day}</span>
                  <div className="mt-0.5 space-y-0.5">
                    {dayTournaments.slice(0, 2).map(t => (
                      <Link
                        key={t.id}
                        href={`/tournaments/${t.id}`}
                        className="block text-xs px-1 py-0.5 rounded truncate text-white"
                        style={{ backgroundColor: 'var(--brand-primary)' }}
                        title={t.name}
                      >
                        {t.name}
                      </Link>
                    ))}
                    {dayTournaments.length > 2 && (
                      <span className="text-xs text-gray-500">+{dayTournaments.length - 2} more</span>
                    )}
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function TournamentsPage() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth());
  const [tournaments, setTournaments] = useState<Tournament[]>([]);
  const [view, setView] = useState<'calendar' | 'list'>('calendar');
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);
  // The calendar grid is unusable at phone widths, so force the list view on
  // small screens. Desktop keeps the calendar/list toggle unchanged.
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.innerWidth < 768
  );
  const effectiveView = isMobile ? 'list' : view;

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, []);

  useEffect(() => {
    fetchTournaments();
  }, [year, month, statusFilter, effectiveView]);

  async function fetchTournaments() {
    setLoading(true);
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || '';
      const params = new URLSearchParams();
      if (effectiveView === 'calendar') {
        // Fetch calendar data
        params.set('year', year.toString());
        params.set('month', (month + 1).toString());
        const res = await fetch(`${backendUrl}/api/tournaments/calendar?${params}`);
        if (res.ok) {
          const data = await res.json();
          setTournaments(data.tournaments || []);
        }
      } else {
        // Fetch list data
        if (statusFilter) params.set('status', statusFilter);
        const res = await fetch(`${backendUrl}/api/tournaments?${params}`);
        if (res.ok) {
          const data = await res.json();
          setTournaments(data.tournaments || []);
        }
      }
    } catch {
      setTournaments([]);
    } finally {
      setLoading(false);
    }
  }

  function prevMonth() {
    if (month === 0) { setMonth(11); setYear(year - 1); }
    else setMonth(month - 1);
  }

  function nextMonth() {
    if (month === 11) { setMonth(0); setYear(year + 1); }
    else setMonth(month + 1);
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Tournaments</h1>
        {!isMobile && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setView('calendar'); }}
              className={`px-3 py-1.5 text-sm rounded-lg ${view === 'calendar' ? 'bg-gray-200 dark:bg-gray-700 font-medium' : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800'}`}
            >
              Calendar
            </button>
            <button
              onClick={() => { setView('list'); }}
              className={`px-3 py-1.5 text-sm rounded-lg ${view === 'list' ? 'bg-gray-200 dark:bg-gray-700 font-medium' : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800'}`}
            >
              List
            </button>
          </div>
        )}
      </div>

      {effectiveView === 'calendar' && (
        <>
          <div className="flex items-center justify-between mb-4">
            <button onClick={prevMonth} className="px-3 py-1 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded">
              &larr; Prev
            </button>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {MONTHS[month]} {year}
            </h2>
            <button onClick={nextMonth} className="px-3 py-1 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded">
              Next &rarr;
            </button>
          </div>
          {loading ? (
            <p className="text-gray-500 dark:text-gray-400 text-center py-8">Loading...</p>
          ) : (
            <CalendarView tournaments={tournaments} year={year} month={month} />
          )}
        </>
      )}

      {effectiveView === 'list' && (
        <>
          <div className="mb-4">
            <select
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
              className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm"
            >
              <option value="">All</option>
              <option value="upcoming">Upcoming</option>
              <option value="registration_open">Registration Open</option>
              <option value="in_progress">In Progress</option>
              <option value="completed">Completed</option>
            </select>
          </div>

          {loading ? (
            <p className="text-gray-500 dark:text-gray-400 text-center py-8">Loading...</p>
          ) : tournaments.length === 0 ? (
            <p className="text-gray-500 dark:text-gray-400 text-center py-8">No tournaments found.</p>
          ) : (
            <div className="space-y-3">
              {tournaments.map(t => (
                <Link
                  key={t.id}
                  href={`/tournaments/${t.id}`}
                  className="block rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 hover:border-blue-300 dark:hover:border-blue-600 transition-colors"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100">{t.name}</h3>
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        {new Date(t.start_date).toLocaleDateString()} — {new Date(t.end_date).toLocaleDateString()}
                        {t.city && ` · ${t.city}`}
                        {t.country && `, ${t.country}`}
                      </p>
                      <div className="flex items-center gap-2 mt-2">
                        <StatusBadge status={t.status} />
                        {t.format && (
                          <span className="text-xs text-gray-500 dark:text-gray-400">{t.format}</span>
                        )}
                        {t.entry_fee > 0 && (
                          <span className="text-xs text-gray-500 dark:text-gray-400">
                            {t.entry_fee} {t.currency}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
