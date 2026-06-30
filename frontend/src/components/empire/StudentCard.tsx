/**
 * Hero block for the Chess Empire personalized homepage.
 *
 * Renders the student's photo (or an initials fallback), full name, branch,
 * coach, current razryad, and current league. Server component — receives
 * a `CEStudentProfile` already fetched by the page.
 */
import { getTranslations } from 'next-intl/server';
import type { CEStudentProfile } from '@/lib/chess-empire-client';

interface StudentCardProps {
  profile: CEStudentProfile;
}

function initials(profile: CEStudentProfile): string {
  const f = (profile.first_name || '').trim();
  const l = (profile.last_name || '').trim();
  const i = `${f.slice(0, 1)}${l.slice(0, 1)}`.toUpperCase();
  return i || '?';
}

export default async function StudentCard({ profile }: StudentCardProps) {
  const t = await getTranslations('empire');
  const fullName = `${profile.first_name ?? ''} ${profile.last_name ?? ''}`.trim() || '—';
  const photo = profile.photo_url || null;

  return (
    <section
      data-testid="empire-student-card"
      className="rounded-2xl border bg-white p-6 md:p-8 flex flex-col md:flex-row items-center gap-6 shadow-sm"
      style={{ borderColor: 'var(--brand-primary, #1a73e8)' }}
    >
      <div className="flex-shrink-0">
        {photo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={photo}
            alt={fullName}
            data-testid="empire-student-photo"
            className="w-24 h-24 md:w-32 md:h-32 rounded-full object-cover border-4"
            style={{ borderColor: 'var(--brand-primary, #1a73e8)' }}
          />
        ) : (
          <div
            data-testid="empire-student-initials"
            className="w-24 h-24 md:w-32 md:h-32 rounded-full flex items-center justify-center text-3xl md:text-4xl font-bold text-white"
            style={{ backgroundColor: 'var(--brand-primary, #1a73e8)' }}
          >
            {initials(profile)}
          </div>
        )}
      </div>

      <div className="flex-1 text-center md:text-left">
        <h1
          className="text-2xl md:text-3xl font-bold mb-2"
          style={{ color: 'var(--brand-primary, #0f172a)' }}
        >
          {fullName}
        </h1>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm text-gray-700">
          <div className="flex gap-2">
            <dt className="font-medium text-gray-500">{t('branchLabel')}</dt>
            <dd>{profile.branch_name || '—'}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="font-medium text-gray-500">{t('coachLabel')}</dt>
            <dd>{profile.coach_name || '—'}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="font-medium text-gray-500">{t('razryadLabel')}</dt>
            <dd>{profile.razryad || '—'}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="font-medium text-gray-500">{t('leagueLabel')}</dt>
            <dd>{profile.current_league || '—'}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
