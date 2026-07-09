/**
 * Chess Empire personalized homepage shell — V1 Player Card visual language.
 *
 * Three states:
 *  - `verified` — dark-slate hero (rating-forward, emerald accent), stat
 *    pills, level progress, rating trend, next lesson, achievements strip.
 *    Greeting sources exclusively from `resolveStudentDisplayName` at the
 *    caller — never from `user.firstName`, an email prefix, or any other
 *    identity source. `null` is a first-class value: the greeting degrades
 *    to a name-less "Welcome back" rather than leaking a fallback.
 *  - `pending_confirm` — email auto-match wrote a soft link; ships the
 *    Phase 4 confirmation banner shape restyled to the dark-slate palette.
 *  - `no_link` — no member row yet. Same name-less copy as Phase 4,
 *    restyled to the dark-slate palette.
 */
import Link from 'next/link';
import { getTranslations } from 'next-intl/server';
import type {
  CEBestBot,
  CERatingPoint,
  CEStudentProfile,
  CEStudentRank,
} from '@/lib/chess-empire-client';
import { getLeague } from '@/lib/league';
import PendingConfirmBanner from './PendingConfirmBanner';

export type EmpireHomeState = 'verified' | 'pending_confirm' | 'no_link';

interface VerifiedProps {
  state: 'verified';
  studentDisplayName: string | null;
  profile: CEStudentProfile;
  ratings: CERatingPoint[];
  rank: CEStudentRank;
  /** Best (max) survival score; null when the student has no survival games. */
  bestSurvivalScore?: number | null;
  /** Highest-rated bot the student has beaten; null when no bot wins yet. */
  bestDefeatedBot?: CEBestBot | null;
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

const ACCENT = '#10B981';
const ACCENT_DIM = '#059669';

/**
 * League tier colors tuned for the dark-slate hero (the light 300-tier of
 * each LeagueBadge tier: C gray, B blue, A purple, Master gold).
 */
const HERO_LEAGUE_COLOR: Record<string, string> = {
  C: '#CBD5E1',
  B: '#93C5FD',
  A: '#C4B5FD',
  Master: '#FDE047',
};

function initialFrom(name: string | null): string {
  if (!name) return '?';
  const trimmed = name.trim();
  return trimmed ? trimmed.slice(0, 1).toUpperCase() : '?';
}

function formatJoined(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
}

interface SparklinePoint {
  x: number;
  y: number;
}

function buildSparkline(
  ratings: CERatingPoint[],
  width: number,
  height: number,
  padX: number,
  padY: number,
): { points: SparklinePoint[]; min: number; max: number } {
  if (ratings.length === 0) return { points: [], min: 0, max: 0 };
  const sorted = [...ratings].sort(
    (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime(),
  );
  const vals = sorted.map((r) => r.rating);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;
  const points = vals.map((v, i) => ({
    x: padX + (i / (vals.length - 1 || 1)) * innerW,
    y: padY + innerH - ((v - min) / span) * innerH,
  }));
  return { points, min, max };
}

function computeDelta(ratings: CERatingPoint[]): number | null {
  if (ratings.length < 2) return null;
  const sorted = [...ratings].sort(
    (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime(),
  );
  const last = sorted[sorted.length - 1];
  const cutoff = new Date(last.date);
  cutoff.setDate(cutoff.getDate() - 30);
  const older =
    sorted.filter((r) => new Date(r.date) <= cutoff).slice(-1)[0] ?? sorted[0];
  return last.rating - older.rating;
}

export default async function EmpireHomePage(props: EmpireHomePageProps) {
  const t = await getTranslations('empire');

  if (props.state === 'no_link') {
    return (
      <main
        data-testid="empire-home-nolink"
        className="min-h-screen px-4 sm:px-6 lg:px-10 py-12 lg:py-20"
        style={{ backgroundColor: '#F6F7F9', color: '#0F172A' }}
      >
        <div className="max-w-2xl mx-auto text-center flex flex-col gap-4">
          <div className="rounded-2xl bg-gradient-to-r from-slate-900 to-slate-700 text-white p-8 sm:p-10 shadow-sm">
            <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">
              {t('welcomeBack')}
            </h1>
            <p className="mt-3 text-slate-300 text-sm">{t('noLinkSubtitle')}</p>
          </div>
          <h2 className="text-lg md:text-xl font-semibold text-slate-800">
            {t('noLinkTitle')}
          </h2>
        </div>
      </main>
    );
  }

  if (props.state === 'pending_confirm') {
    if (!props.studentDisplayName) {
      return (
        <main
          data-testid="empire-home-nolink"
          className="min-h-screen px-4 sm:px-6 lg:px-10 py-12 lg:py-20"
          style={{ backgroundColor: '#F6F7F9', color: '#0F172A' }}
        >
          <div className="max-w-2xl mx-auto text-center flex flex-col gap-4">
            <div className="rounded-2xl bg-gradient-to-r from-slate-900 to-slate-700 text-white p-8 sm:p-10 shadow-sm">
              <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">
                {t('welcomeBack')}
              </h1>
              <p className="mt-3 text-slate-300 text-sm">{t('noLinkSubtitle')}</p>
            </div>
            <h2 className="text-lg md:text-xl font-semibold text-slate-800">
              {t('noLinkTitle')}
            </h2>
          </div>
        </main>
      );
    }

    return (
      <main
        data-testid="empire-home-pending"
        className="min-h-screen px-4 sm:px-6 lg:px-10 py-8 lg:py-12"
        style={{ backgroundColor: '#F6F7F9', color: '#0F172A' }}
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
    rank,
    bestSurvivalScore = null,
    bestDefeatedBot = null,
  } = props;

  const survivorSubtitle =
    bestSurvivalScore != null ? String(bestSurvivalScore) : '—';
  const botSlayerSubtitle = bestDefeatedBot
    ? `${bestDefeatedBot.name} · ${bestDefeatedBot.rating}`
    : '—';

  const greeting = studentDisplayName
    ? t('welcomeBackNamed', { name: studentDisplayName })
    : t('welcomeBack');

  const sortedRatings = [...ratings].sort(
    (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime(),
  );
  const currentRating =
    sortedRatings.length > 0
      ? sortedRatings[sortedRatings.length - 1].rating
      : profile.current_rating ?? null;
  const delta = computeDelta(sortedRatings);
  const trend = buildSparkline(sortedRatings, 480, 120, 8, 8);
  const trendPointsStr = trend.points
    .map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(' ');

  const LESSONS_PER_LEVEL = 15;
  const totalLessons = profile.total_lessons ?? 120;
  const currentLesson = profile.current_lesson ?? 0;
  const lessonsRemaining = Math.max(0, totalLessons - currentLesson);

  const derivedLevel =
    currentLesson <= 0
      ? 1
      : Math.max(1, Math.min(8, Math.ceil(currentLesson / LESSONS_PER_LEVEL)));
  const currentLevel =
    profile.current_level && profile.current_level >= 1 && profile.current_level <= 8
      ? profile.current_level
      : derivedLevel;

  const isFinalLevel = currentLevel >= 8;
  const nextLevel = isFinalLevel ? currentLevel : currentLevel + 1;
  const lessonsUntilNextLevel = isFinalLevel
    ? lessonsRemaining
    : Math.max(0, currentLevel * LESSONS_PER_LEVEL - currentLesson);
  const progressCopy = isFinalLevel
    ? t('lessonsRemaining', { count: lessonsRemaining })
    : t('lessonsUntilNextLevel', { count: lessonsUntilNextLevel, nextLevel });

  const razryad = profile.razryad ?? null;
  const branchName = profile.branch_name ?? null;
  const coachName = profile.coach_name ?? null;
  const joined = formatJoined(profile.joined_at);

  const deltaLabel =
    delta === null
      ? null
      : `${delta >= 0 ? '+' : ''}${delta} ${t('ratingDeltaSuffix')}`;

  const rawLeague = profile.current_league?.trim();
  const heroLeague =
    rawLeague && rawLeague.length > 0
      ? rawLeague
      : currentRating != null
        ? getLeague(currentRating)
        : null;
  const heroLeagueColor = heroLeague
    ? HERO_LEAGUE_COLOR[heroLeague] ?? '#FFFFFF'
    : '#FFFFFF';

  return (
    <main
      data-testid="empire-home"
      className="min-h-screen px-4 sm:px-6 lg:px-10 py-8 lg:py-12"
      style={{ backgroundColor: '#F6F7F9', color: '#0F172A' }}
    >
      <div className="max-w-5xl mx-auto flex flex-col gap-6">
        {/* Hero */}
        <section
          data-testid="empire-hero"
          className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-slate-900 to-slate-700 shadow-sm text-white"
        >
          <div className="p-6 sm:p-8 flex flex-col sm:flex-row sm:items-center gap-6">
            <div className="shrink-0 relative">
              {profile.photo_url ? (
                <img
                  data-testid="empire-avatar"
                  src={profile.photo_url}
                  alt={studentDisplayName ?? ''}
                  className="w-24 h-24 rounded-full object-cover ring-4"
                  style={{
                    boxShadow: `0 0 0 3px rgba(16,185,129,0.35)`,
                    ['--tw-ring-color' as string]: ACCENT,
                  }}
                />
              ) : (
                <div
                  data-testid="empire-avatar"
                  className="w-24 h-24 rounded-full grid place-items-center text-2xl font-bold ring-4"
                  style={{
                    background: `linear-gradient(135deg, ${ACCENT}, #0EA5A5)`,
                    boxShadow: `0 0 0 3px rgba(16,185,129,0.35)`,
                    ['--tw-ring-color' as string]: ACCENT,
                  }}
                >
                  {initialFrom(studentDisplayName)}
                </div>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                {razryad && (
                  <span
                    data-testid="empire-razryad-chip"
                    className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider border"
                    style={{
                      backgroundColor: 'rgba(16,185,129,0.15)',
                      color: '#6EE7B7',
                      borderColor: 'rgba(16,185,129,0.3)',
                    }}
                  >
                    {razryad}
                  </span>
                )}
                <span className="text-xs uppercase tracking-wider text-slate-400 font-medium">
                  {t('playerLabel')}
                </span>
              </div>
              <h1
                data-testid="empire-home-greeting"
                className="text-2xl sm:text-3xl font-semibold tracking-tight leading-tight"
              >
                {greeting}
              </h1>
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-300">
                {coachName && (
                  <span
                    data-testid="empire-coach-chip"
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
                      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                      <circle cx="12" cy="7" r="4" />
                    </svg>
                    <span>{coachName}</span>
                  </span>
                )}
                {branchName && (
                  <span
                    data-testid="empire-branch-chip"
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
                {joined && (
                  <span className="inline-flex items-center gap-1.5">
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
                      <rect x="3" y="4" width="18" height="18" rx="2" />
                      <path d="M16 2v4M8 2v4M3 10h18" />
                    </svg>
                    <span>{t('joinedSince', { since: joined })}</span>
                  </span>
                )}
              </div>
            </div>
            <div className="shrink-0">
              <div className="flex items-start gap-6 sm:justify-end">
                {/* Rating column */}
                <div className="sm:text-right">
                  <div className="text-[11px] uppercase tracking-widest text-slate-400 font-semibold">
                    {t('ratingTitle')}
                  </div>
                  <div className="mt-1 flex items-center gap-2 sm:justify-end">
                    <span
                      className="text-3xl leading-none"
                      aria-hidden="true"
                    >
                      📈
                    </span>
                    <span
                      data-testid="empire-rating-value"
                      className="text-5xl font-bold leading-none"
                      style={{ fontVariantNumeric: 'tabular-nums' }}
                    >
                      {currentRating ?? '—'}
                    </span>
                  </div>
                </div>
                {/* Divider */}
                <div
                  className="self-stretch w-px bg-white/[.14]"
                  aria-hidden="true"
                />
                {/* League column */}
                <div className="sm:text-right">
                  <div className="text-[11px] uppercase tracking-widest text-slate-400 font-semibold">
                    {t('leagueLabel')}
                  </div>
                  <div className="mt-1 flex items-center gap-2 sm:justify-end">
                    {heroLeague ? (
                      <>
                        <span
                          className="text-3xl leading-none"
                          aria-hidden="true"
                        >
                          🏆
                        </span>
                        <span
                          data-testid="empire-league-value"
                          className="text-5xl font-bold leading-none"
                          style={{ color: heroLeagueColor }}
                        >
                          {heroLeague}
                        </span>
                      </>
                    ) : (
                      <span
                        data-testid="empire-league-value"
                        className="text-5xl font-bold leading-none text-white"
                      >
                        —
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Stat pills */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-white border border-slate-200 shadow-sm px-4 py-3">
            <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
              {t('rankSchoolLabel')}
            </div>
            <div className="mt-1 flex items-baseline gap-1">
              <span
                data-testid="empire-school-rank"
                className="text-xl font-bold"
                style={{ fontVariantNumeric: 'tabular-nums' }}
              >
                {rank.school_rank !== null ? `#${rank.school_rank}` : '—'}
              </span>
              {rank.school_size !== null && (
                <span className="text-sm text-slate-500" style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {t('ofSize', { size: rank.school_size })}
                </span>
              )}
            </div>
          </div>
          <div className="rounded-xl bg-white border border-slate-200 shadow-sm px-4 py-3">
            <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
              {t('rankBranchLabel')}
            </div>
            <div className="mt-1 flex items-baseline gap-1">
              <span
                data-testid="empire-branch-rank"
                className={`text-xl font-bold ${rank.branch_rank === null ? 'text-slate-400' : ''}`}
                style={{ fontVariantNumeric: 'tabular-nums' }}
              >
                {rank.branch_rank !== null ? `#${rank.branch_rank}` : '—'}
              </span>
              {rank.branch_size !== null && (
                <span className="text-sm text-slate-500" style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {t('ofSize', { size: rank.branch_size })}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Progress + Trend */}
        <div className="grid md:grid-cols-2 gap-3">
          <section
            data-testid="empire-progress"
            className="rounded-2xl bg-white border border-slate-200 shadow-sm p-5"
          >
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
                  {t('levelLabel')}
                </div>
                <div className="mt-1 flex items-baseline gap-2">
                  <span
                    data-testid="empire-progress-level"
                    className="text-2xl font-bold"
                    style={{ fontVariantNumeric: 'tabular-nums' }}
                  >
                    {profile.current_level ?? '—'}
                  </span>
                </div>
              </div>
              <div className="text-right">
                <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
                  {t('lessonLabel')}
                </div>
                <div
                  className="mt-1 text-sm text-slate-700"
                  style={{ fontVariantNumeric: 'tabular-nums' }}
                >
                  <span data-testid="empire-progress-current" className="font-bold">
                    {currentLesson}
                  </span>
                  <span className="text-slate-400"> / {totalLessons}</span>
                </div>
              </div>
            </div>
            <div
              data-testid="empire-progress-bar"
              role="progressbar"
              aria-valuenow={Math.round((currentLesson / totalLessons) * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
              className="mt-4"
            >
              <div className="flex gap-1.5">
                {Array.from({ length: 8 }, (_, s) => {
                  const level = s + 1;
                  const isCurrent = level === currentLevel;
                  return (
                    <div
                      key={s}
                      data-testid={`empire-progress-segment-${level}`}
                      title={t('journeyStepTitle', { level, total: 15 })}
                      className={`flex-1 flex gap-[1px] p-0.5 rounded-md ${
                        isCurrent ? 'ring-2 ring-emerald-500/50 bg-emerald-50/60' : ''
                      }`}
                    >
                      {isCurrent && (
                        <span
                          data-testid="empire-progress-segment-current"
                          className="sr-only"
                          aria-hidden="true"
                        />
                      )}
                      {Array.from({ length: 15 }, (_, k) => {
                        const lesson = s * 15 + k + 1;
                        const filled = lesson <= currentLesson;
                        return (
                          <div
                            key={k}
                            className="flex-1 h-2.5 rounded-sm"
                            style={{
                              background: filled
                                ? `linear-gradient(90deg, ${ACCENT_DIM}, ${ACCENT})`
                                : '#E5E7EB',
                            }}
                          />
                        );
                      })}
                    </div>
                  );
                })}
              </div>
              <div className="mt-2 flex gap-1.5">
                {Array.from({ length: 8 }, (_, i) => {
                  const level = i + 1;
                  const cls =
                    level === currentLevel
                      ? 'text-emerald-600 font-bold'
                      : level < currentLevel
                        ? 'text-slate-700'
                        : 'text-slate-400';
                  return (
                    <div
                      key={i}
                      className={`flex-1 text-center text-[11px] ${cls}`}
                    >
                      {level}
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="mt-3 text-sm text-slate-600">
              {progressCopy}
            </div>
          </section>

          <section
            data-testid="empire-rating-trend"
            className="rounded-2xl bg-white border border-slate-200 shadow-sm p-5"
          >
            <div className="flex items-start justify-between">
              <div>
                <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
                  {t('trendTitle')}
                </div>
                <div
                  className="mt-1 text-sm text-slate-700"
                  style={{ fontVariantNumeric: 'tabular-nums' }}
                >
                  {t('trendSubtitle')}
                </div>
              </div>
              <div className="text-right">
                {deltaLabel && (
                  <div
                    className={`text-sm font-semibold ${
                      delta! >= 0 ? 'text-emerald-600' : 'text-rose-600'
                    }`}
                    style={{ fontVariantNumeric: 'tabular-nums' }}
                  >
                    {deltaLabel}
                  </div>
                )}
                {trend.points.length > 0 && (
                  <div
                    className="text-xs text-slate-500"
                    style={{ fontVariantNumeric: 'tabular-nums' }}
                  >
                    {trend.min} — {trend.max}
                  </div>
                )}
              </div>
            </div>
            {trend.points.length > 0 ? (
              <svg
                data-testid="empire-trend-chart"
                width="100%"
                height={120}
                viewBox="0 0 480 120"
                preserveAspectRatio="none"
                className="mt-3"
                role="img"
                aria-label={t('trendTitle')}
              >
                <defs>
                  <linearGradient id="empire-trend-grad" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor={ACCENT} stopOpacity={0.35} />
                    <stop offset="100%" stopColor={ACCENT} stopOpacity={0} />
                  </linearGradient>
                </defs>
                {[0.25, 0.5, 0.75].map((r) => (
                  <line
                    key={r}
                    x1={8}
                    x2={472}
                    y1={(120 * r).toFixed(1)}
                    y2={(120 * r).toFixed(1)}
                    stroke="#E2E8F0"
                    strokeDasharray="2 3"
                  />
                ))}
                <polygon
                  fill="url(#empire-trend-grad)"
                  points={`8,112 ${trendPointsStr} 472,112`}
                />
                <polyline
                  fill="none"
                  stroke={ACCENT}
                  strokeWidth={2}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  points={trendPointsStr}
                />
                <circle
                  cx={trend.points[trend.points.length - 1].x}
                  cy={trend.points[trend.points.length - 1].y}
                  r={3.5}
                  fill={ACCENT}
                  stroke="white"
                  strokeWidth={2}
                />
              </svg>
            ) : (
              <p
                data-testid="empire-trend-empty"
                className="mt-3 text-sm text-slate-500"
              >
                {t('ratingEmpty')}
              </p>
            )}
          </section>
        </div>

        {/* Next lesson */}
        <section
          data-testid="empire-next-lesson"
          className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5"
        >
          <div className="flex flex-col sm:flex-row sm:items-center gap-4">
            <div
              className="w-12 h-12 rounded-xl grid place-items-center text-white text-lg font-bold shrink-0"
              style={{ background: `linear-gradient(135deg, ${ACCENT}, #0EA5A5)` }}
              aria-hidden="true"
            >
              {initialFrom(studentDisplayName)}
            </div>
            <div className="flex-1">
              <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
                {t('nextLessonTitle')}
              </div>
              <div className="mt-1 text-lg font-semibold tracking-tight">
                {t('nextLessonPlaceholder')}
              </div>
              {(coachName || branchName) && (
                <div className="text-sm text-slate-600">
                  {coachName ? t('withCoach', { coach: coachName }) : ''}
                  {coachName && branchName ? ' · ' : ''}
                  {branchName ?? ''}
                </div>
              )}
            </div>
            <Link
              href="/learn"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-slate-900 text-white text-sm font-semibold hover:bg-slate-800 transition"
            >
              {t('prepareCta')}
              <svg
                width={14}
                height={14}
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2.5}
                aria-hidden="true"
              >
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </Link>
          </div>
        </section>

        {/* Achievements strip */}
        <section data-testid="empire-achievements">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-500">
              {t('achievementsTitle')}
            </h2>
          </div>
          <ul
            data-testid="empire-highlight-cards"
            className="grid grid-cols-2 gap-3 mb-3"
          >
            <li
              data-testid="empire-card-survivor"
              className="rounded-xl border border-slate-200 bg-white p-3 flex items-center gap-3"
            >
              <div
                className="w-10 h-10 rounded-lg grid place-items-center shrink-0"
                style={{
                  backgroundColor: 'rgba(16,185,129,0.12)',
                  color: ACCENT_DIM,
                }}
                aria-hidden="true"
              >
                <svg
                  width={20}
                  height={20}
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
              </div>
              <div className="min-w-0">
                <div className="text-xs font-semibold text-slate-800 leading-snug">
                  {t('survivorTitle')}
                </div>
                <div
                  data-testid="empire-card-survivor-value"
                  className="text-sm text-slate-600 mt-0.5 truncate"
                >
                  {survivorSubtitle}
                </div>
              </div>
            </li>
            <li
              data-testid="empire-card-bot-slayer"
              className="rounded-xl border border-slate-200 bg-white p-3 flex items-center gap-3"
            >
              <div
                className="w-10 h-10 rounded-lg grid place-items-center shrink-0"
                style={{
                  backgroundColor: 'rgba(16,185,129,0.12)',
                  color: ACCENT_DIM,
                }}
                aria-hidden="true"
              >
                <svg
                  width={20}
                  height={20}
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <rect x="4" y="8" width="16" height="11" rx="2" />
                  <path d="M12 8V4M9 13h.01M15 13h.01" />
                </svg>
              </div>
              <div className="min-w-0">
                <div className="text-xs font-semibold text-slate-800 leading-snug">
                  {t('botSlayerTitle')}
                </div>
                <div
                  data-testid="empire-card-bot-slayer-value"
                  className="text-sm text-slate-600 mt-0.5 truncate"
                >
                  {botSlayerSubtitle}
                </div>
              </div>
            </li>
          </ul>
        </section>
      </div>
    </main>
  );
}
