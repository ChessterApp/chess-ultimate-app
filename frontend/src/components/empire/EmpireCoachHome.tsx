/**
 * Chess Empire personalized homepage — coach variant.
 *
 * Coaches link through the same invite flow as students but their UUID lives
 * in the CE `coaches` table, so the student profile API 404s for them. This
 * variant renders a coach-appropriate home: avatar (photo or initials fallback),
 * branch name, own-roster stats (total / with razryad / league breakdown), the
 * coach bio, and a roster list. Every enrichment prop is optional so the page
 * still renders a bare greeting when the CE API is unavailable.
 *
 * Visual language mirrors the student home (`EmpireHomePage`): dark-slate hero
 * with an emerald-accented avatar, white stat cards, slate typography.
 */
import { getTranslations } from 'next-intl/server';
import type { CEActiveStudent } from '@/lib/chess-empire-client';
import type { CoachHomeStats } from '@/lib/empire-coach-stats';

const ACCENT = '#10B981';

function initialFrom(name: string | null): string {
  if (!name) return '?';
  const trimmed = name.trim();
  return trimmed ? trimmed.slice(0, 1).toUpperCase() : '?';
}

function studentName(s: CEActiveStudent): string {
  return `${s.first_name ?? ''} ${s.last_name ?? ''}`.trim() || '—';
}

const EMPTY_STATS: CoachHomeStats = {
  total: 0,
  withRazryad: 0,
  leagueBreakdown: [],
};

export default async function EmpireCoachHome({
  coachDisplayName,
  photoUrl = null,
  bio = null,
  branchName = null,
  stats = EMPTY_STATS,
  roster = [],
}: {
  coachDisplayName: string | null;
  photoUrl?: string | null;
  bio?: string | null;
  branchName?: string | null;
  stats?: CoachHomeStats;
  roster?: CEActiveStudent[];
}) {
  const t = await getTranslations('empire');
  const greeting = coachDisplayName
    ? t('coachWelcomeNamed', { name: coachDisplayName })
    : t('coachWelcome');

  return (
    <main
      data-testid="empire-home-coach"
      className="min-h-screen px-4 sm:px-6 lg:px-10 py-8 lg:py-12"
      style={{ backgroundColor: '#F6F7F9', color: '#0F172A' }}
    >
      <div className="max-w-5xl mx-auto flex flex-col gap-6">
        {/* Hero */}
        <section
          data-testid="empire-coach-hero"
          className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-slate-900 to-slate-700 shadow-sm text-white"
        >
          <div className="p-6 sm:p-8 flex flex-col sm:flex-row sm:items-center gap-6">
            <div className="shrink-0">
              {photoUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  data-testid="empire-coach-avatar"
                  src={photoUrl}
                  alt={coachDisplayName ?? ''}
                  className="w-24 h-24 rounded-full object-cover ring-4"
                  style={{
                    boxShadow: `0 0 0 3px rgba(16,185,129,0.35)`,
                    ['--tw-ring-color' as string]: ACCENT,
                  }}
                />
              ) : (
                <div
                  data-testid="empire-coach-avatar"
                  className="w-24 h-24 rounded-full grid place-items-center text-2xl font-bold ring-4"
                  style={{
                    background: `linear-gradient(135deg, ${ACCENT}, #0EA5A5)`,
                    boxShadow: `0 0 0 3px rgba(16,185,129,0.35)`,
                    ['--tw-ring-color' as string]: ACCENT,
                  }}
                >
                  {initialFrom(coachDisplayName)}
                </div>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <span className="text-xs uppercase tracking-wider text-slate-400 font-medium">
                {t('coachRoleLabel')}
              </span>
              <h1
                data-testid="empire-coach-greeting"
                className="text-2xl sm:text-3xl font-semibold tracking-tight leading-tight mt-1"
              >
                {greeting}
              </h1>
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-300">
                {branchName && (
                  <span
                    data-testid="empire-coach-branch"
                    className="inline-flex items-center gap-1.5"
                  >
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={2}
                      className="text-slate-400"
                      aria-hidden="true"
                    >
                      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                      <circle cx="12" cy="10" r="3" />
                    </svg>
                    <span>{branchName}</span>
                  </span>
                )}
                <span>{t('coachHomeSubtitle')}</span>
              </div>
            </div>
          </div>
        </section>

        {/* Stat cards */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-white border border-slate-200 shadow-sm px-4 py-3">
            <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
              {t('coachStudentsLabel')}
            </div>
            <div
              data-testid="empire-coach-total"
              className="mt-1 text-xl font-bold"
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              {stats.total}
            </div>
          </div>
          <div className="rounded-xl bg-white border border-slate-200 shadow-sm px-4 py-3">
            <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
              {t('coachWithRazryadLabel')}
            </div>
            <div
              data-testid="empire-coach-razryad-count"
              className="mt-1 text-xl font-bold"
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              {stats.withRazryad}
            </div>
          </div>
        </div>

        {/* League breakdown */}
        <section
          data-testid="empire-coach-leagues"
          className="rounded-2xl bg-white border border-slate-200 shadow-sm p-5"
        >
          <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
            {t('coachLeagueBreakdownLabel')}
          </div>
          {stats.leagueBreakdown.length > 0 ? (
            <ul className="mt-3 flex flex-wrap gap-2">
              {stats.leagueBreakdown.map((l) => (
                <li
                  key={l.league}
                  data-testid="empire-coach-league-pill"
                  className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-sm"
                >
                  <span className="font-semibold text-slate-800">
                    {l.league}
                  </span>
                  <span
                    className="text-slate-500"
                    style={{ fontVariantNumeric: 'tabular-nums' }}
                  >
                    {l.count}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-slate-500">
              {t('coachLeagueEmpty')}
            </p>
          )}
        </section>

        {/* Bio */}
        {bio && bio.trim() && (
          <section
            data-testid="empire-coach-bio"
            className="rounded-2xl bg-white border border-slate-200 shadow-sm p-5"
          >
            <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
              {t('coachBioTitle')}
            </div>
            <p className="mt-2 text-sm text-slate-700 whitespace-pre-line">
              {bio}
            </p>
          </section>
        )}

        {/* Roster */}
        <section data-testid="empire-coach-roster">
          <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-500 mb-3">
            {t('coachRosterTitle')}
          </h2>
          {roster.length > 0 ? (
            <ul className="flex flex-col gap-2">
              {roster.map((s) => (
                <li
                  key={s.id}
                  data-testid="empire-coach-roster-row"
                  className="rounded-xl bg-white border border-slate-200 shadow-sm px-4 py-3 flex items-center gap-3"
                >
                  <div
                    className="w-10 h-10 rounded-full grid place-items-center text-sm font-bold text-white shrink-0"
                    style={{
                      background: `linear-gradient(135deg, ${ACCENT}, #0EA5A5)`,
                    }}
                    aria-hidden="true"
                  >
                    {initialFrom(studentName(s))}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-slate-800 truncate">
                      {studentName(s)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {s.current_razryad &&
                      s.current_razryad.trim().toLowerCase() !== 'none' && (
                        <span
                          data-testid="empire-coach-roster-razryad"
                          className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider border"
                          style={{
                            backgroundColor: 'rgba(16,185,129,0.12)',
                            color: '#059669',
                            borderColor: 'rgba(16,185,129,0.3)',
                          }}
                        >
                          {s.current_razryad}
                        </span>
                      )}
                    {s.current_league && (
                      <span
                        data-testid="empire-coach-roster-league"
                        className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs font-semibold text-slate-700"
                      >
                        {s.current_league}
                      </span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p
              data-testid="empire-coach-roster-empty"
              className="text-sm text-slate-500"
            >
              {t('coachRosterEmpty')}
            </p>
          )}
        </section>
      </div>
    </main>
  );
}
