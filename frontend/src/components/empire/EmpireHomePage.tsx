/**
 * Chess Empire personalized homepage shell.
 *
 * Handles three membership states:
 *  - `verified` — full personalized layout (student card, progress, rating,
 *    achievements). Hero greeting sources from `studentDisplayName`.
 *  - `pending_confirm` — email auto-match wrote a soft link. Shows a
 *    confirmation banner ("Is this you, {name}?") gating the personalized
 *    surface behind explicit user consent.
 *  - `no_link` — no member row yet. Shows name-less "we're getting your
 *    profile ready" copy. Never uses email-derived or Clerk-derived names.
 *
 * `studentDisplayName` must come from `resolveStudentDisplayName` at the
 * caller. `null` is a first-class value here — the component renders
 * name-less copy rather than leaking an email prefix.
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
import PendingConfirmBanner from './PendingConfirmBanner';

const RatingTrend = dynamic(() => import('./RatingTrend'));

export type EmpireHomeState = 'verified' | 'pending_confirm' | 'no_link';

interface VerifiedProps {
  state: 'verified';
  studentDisplayName: string | null;
  profile: CEStudentProfile;
  ratings: CERatingPoint[];
  achievements: CEAchievement[];
  rank: CEStudentRank;
}

interface PendingConfirmProps {
  state: 'pending_confirm';
  studentDisplayName: string | null;
}

interface NoLinkProps {
  state: 'no_link';
  studentDisplayName: null;
}

export type EmpireHomePageProps = VerifiedProps | PendingConfirmProps | NoLinkProps;

function hasRank(rank: CEStudentRank): boolean {
  return rank.branch_rank !== null || rank.school_rank !== null;
}

export default async function EmpireHomePage(props: EmpireHomePageProps) {
  const t = await getTranslations('empire');

  if (props.state === 'no_link') {
    return (
      <main
        data-testid="empire-home-nolink"
        className="min-h-screen bg-white px-4 sm:px-6 lg:px-10 py-12 lg:py-20"
      >
        <div className="max-w-2xl mx-auto text-center flex flex-col gap-4">
          <h1
            className="text-3xl md:text-4xl font-bold"
            style={{ color: 'var(--brand-primary, #0f172a)' }}
          >
            {t('welcomeBack')}
          </h1>
          <h2 className="text-xl md:text-2xl font-semibold text-gray-800">
            {t('noLinkTitle')}
          </h2>
          <p className="text-base text-gray-600">
            {t('noLinkSubtitle')}
          </p>
        </div>
      </main>
    );
  }

  if (props.state === 'pending_confirm') {
    // Never render the confirmation card without a real name — the plan
    // forbids email/Clerk fallbacks. Data-integrity fallback: no name means
    // the row shouldn't have been written; degrade to no_link copy.
    if (!props.studentDisplayName) {
      return (
        <main
          data-testid="empire-home-nolink"
          className="min-h-screen bg-white px-4 sm:px-6 lg:px-10 py-12 lg:py-20"
        >
          <div className="max-w-2xl mx-auto text-center flex flex-col gap-4">
            <h1
              className="text-3xl md:text-4xl font-bold"
              style={{ color: 'var(--brand-primary, #0f172a)' }}
            >
              {t('welcomeBack')}
            </h1>
            <h2 className="text-xl md:text-2xl font-semibold text-gray-800">
              {t('noLinkTitle')}
            </h2>
            <p className="text-base text-gray-600">{t('noLinkSubtitle')}</p>
          </div>
        </main>
      );
    }

    return (
      <main
        data-testid="empire-home-pending"
        className="min-h-screen bg-white px-4 sm:px-6 lg:px-10 py-8 lg:py-12"
      >
        <div className="max-w-2xl mx-auto flex flex-col gap-6">
          <PendingConfirmBanner displayName={props.studentDisplayName} />
        </div>
      </main>
    );
  }

  const {
    studentDisplayName,
    profile,
    ratings,
    achievements,
    rank,
  } = props;

  const greeting = studentDisplayName
    ? t('welcomeBackNamed', { name: studentDisplayName })
    : t('welcomeBack');

  return (
    <main
      data-testid="empire-home"
      className="min-h-screen bg-white px-4 sm:px-6 lg:px-10 py-8 lg:py-12"
    >
      <div className="max-w-5xl mx-auto flex flex-col gap-6">
        <h1
          data-testid="empire-home-greeting"
          className="text-2xl md:text-3xl font-bold"
          style={{ color: 'var(--brand-primary, #0f172a)' }}
        >
          {greeting}
        </h1>

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
