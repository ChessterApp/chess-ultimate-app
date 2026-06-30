/**
 * Chess Empire personalized homepage shell.
 *
 * Composes StudentCard + ProgressBar + RatingTrend + Achievements + a
 * "Continue learning" CTA into a single dashboard layout. Rendered by
 * `frontend/src/app/page.tsx` when a signed-in CE student visits apex
 * `chess-empire.chesster.io/` and has a verified `external_student_id`
 * link in `organization_members`.
 *
 * RatingTrend is the only client component in the tree — it's lazy-imported
 * via `next/dynamic` so the rest of the homepage stays in the server bundle.
 */
import Link from 'next/link';
import dynamic from 'next/dynamic';
import { getTranslations } from 'next-intl/server';
import type {
  CEAchievement,
  CERatingPoint,
  CEStudentProfile,
  CEStudentRank,
} from '@/lib/chess-empire-client';
import StudentCard from './StudentCard';
import ProgressBar from './ProgressBar';
import Achievements from './Achievements';

const RatingTrend = dynamic(() => import('./RatingTrend'));

export interface EmpireHomePageProps {
  profile: CEStudentProfile;
  ratings: CERatingPoint[];
  achievements: CEAchievement[];
  rank: CEStudentRank;
}

function hasRank(rank: CEStudentRank): boolean {
  return rank.branch_rank !== null || rank.school_rank !== null;
}

export default async function EmpireHomePage({
  profile,
  ratings,
  achievements,
  rank,
}: EmpireHomePageProps) {
  const t = await getTranslations('empire');

  return (
    <main
      data-testid="empire-home"
      className="min-h-screen bg-white px-4 sm:px-6 lg:px-10 py-8 lg:py-12"
    >
      <div className="max-w-5xl mx-auto flex flex-col gap-6">
        <StudentCard profile={profile} />

        {hasRank(rank) && (
          <section
            data-testid="empire-rank"
            className="rounded-2xl border bg-white p-4 md:p-5 shadow-sm flex flex-wrap items-center gap-3 text-sm"
            style={{ borderColor: 'var(--brand-primary, #1a73e8)' }}
          >
            {rank.branch_rank !== null && (
              <span
                className="px-3 py-1 rounded-full text-white text-xs font-semibold"
                style={{ backgroundColor: 'var(--brand-primary, #1a73e8)' }}
              >
                {t('rankBranch', {
                  rank: rank.branch_rank,
                  size: rank.branch_size ?? '?',
                })}
              </span>
            )}
            {rank.school_rank !== null && (
              <span
                className="px-3 py-1 rounded-full text-white text-xs font-semibold"
                style={{ backgroundColor: 'var(--brand-accent, #ffd700)', color: '#0f172a' }}
              >
                {t('rankSchool', {
                  rank: rank.school_rank,
                  size: rank.school_size ?? '?',
                })}
              </span>
            )}
          </section>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ProgressBar
            current={profile.current_lesson ?? null}
            total={profile.total_lessons ?? null}
            level={profile.current_level ?? null}
          />
          <RatingTrend points={ratings} />
        </div>

        <Achievements achievements={achievements} />

        <div className="flex justify-center">
          <Link
            href="/learn"
            data-testid="empire-continue-cta"
            className="inline-block px-6 py-3 rounded-xl font-semibold text-white shadow-sm transition-transform hover:scale-105"
            style={{ backgroundColor: 'var(--brand-primary, #1a73e8)' }}
          >
            {t('continueCta')}
          </Link>
        </div>
      </div>
    </main>
  );
}
