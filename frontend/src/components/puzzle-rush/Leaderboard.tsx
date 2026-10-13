'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { rushApi, RushApiError, type RushAuth } from '@/lib/puzzle-rush/api';
import type {
  LeaderboardResponse,
  RushMode,
  RushPeriod,
  RushScope,
  SchoolLeaderboardResponse,
  SchoolPeriod,
  SchoolScope,
  SchoolStudent,
} from '@/lib/puzzle-rush/types';
import StudentPicker from './StudentPicker';
import styles from './PuzzleRush.module.css';

export type BoardScope = RushScope | SchoolScope;

const PERIODS: RushPeriod[] = ['daily', 'weekly', 'all'];
const SCHOOL_PERIODS: SchoolPeriod[] = ['week', 'month', 'all'];
const SCOPES: RushScope[] = ['global', 'personal'];
const ALL_SCOPES: BoardScope[] = [...SCOPES, 'school', 'branch'];
const MEDAL = [styles.rankGold, styles.rankSilver, styles.rankBronze];

const isSchool = (s: BoardScope): s is SchoolScope => s === 'school' || s === 'branch';

interface Props {
  mode: RushMode;
  auth: () => RushAuth;
  isGuest: boolean;
  userId: string | null;
  signInHref: string;
  /** Bump to refetch (e.g. after a run ends). */
  refreshKey?: string;
  /** Scope to open on (the results modal links straight to School). */
  initialScope?: BoardScope;
  /** Family accounts: linked students already known (e.g. from the last run's picker). */
  students?: SchoolStudent[];
}

interface Loaded {
  key: string;
  board?: LeaderboardResponse;
  schoolBoard?: SchoolLeaderboardResponse;
  error?: unknown;
}

function Seg<T extends string>({ value, options, label, onChange }: {
  value: T; options: T[]; label: (v: T) => string; onChange: (v: T) => void;
}) {
  return (
    <div className={styles.seg} role="tablist">
      {options.map((o) => (
        <button
          key={o}
          type="button"
          role="tab"
          aria-selected={o === value}
          className={`${styles.segButton} ${o === value ? styles.segOn : ''}`}
          onClick={() => onChange(o)}
        >
          {label(o)}
        </button>
      ))}
    </div>
  );
}

function Rank({ n }: { n: number }) {
  return <span className={`${styles.rank} ${n <= 3 ? MEDAL[n - 1] : ''}`}>#{n}</span>;
}

/**
 * S11: Global | Personal × Daily | Weekly | All-time, own row pinned first.
 * Survival, signed in: also School | Branch (Chess Empire) × Week | Month | All-time.
 */
export default function Leaderboard({
  mode, auth, isGuest, userId, signInHref, refreshKey = '', initialScope = 'global', students,
}: Props) {
  const t = useTranslations('puzzleRush.leaderboard');
  const scopes = mode === 'survival' && !isGuest ? ALL_SCOPES : SCOPES;
  const [pickedScope, setPickedScope] = useState<BoardScope>(initialScope);
  const scope = scopes.includes(pickedScope) ? pickedScope : 'global';
  const school = isSchool(scope);
  const [period, setPeriod] = useState<RushPeriod>('daily');
  const [schoolPeriod, setSchoolPeriod] = useState<SchoolPeriod>('week');
  const [studentId, setStudentId] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<SchoolStudent[]>([]);
  const known = candidates.length > 0 ? candidates : students ?? [];
  const needsSignIn = scope === 'personal' && isGuest;
  // Each response is tagged with the query it answers; anything else is "loading".
  const queryKey = school
    ? `${scope}|${schoolPeriod}|${studentId}|${refreshKey}`
    : `${mode}|${period}|${scope}|${isGuest}|${refreshKey}`;
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const status = loaded?.key !== queryKey ? 'loading' : loaded.error === undefined ? 'ready' : 'error';
  const error = status === 'error' && loaded!.error instanceof RushApiError ? loaded!.error : null;

  useEffect(() => {
    if (needsSignIn) return;
    let live = true;
    const req: Promise<Omit<Loaded, 'key'>> = isSchool(scope)
      ? rushApi.schoolLeaderboard(auth(), scope, schoolPeriod, studentId).then((d) => ({ schoolBoard: d }))
      : rushApi.leaderboard(auth(), mode, period, scope).then((d) => ({ board: d }));
    req
      .then((r) => { if (live) setLoaded({ key: queryKey, ...r }); })
      .catch((e: unknown) => {
        if (!live) return;
        setLoaded({ key: queryKey, error: e ?? null });
        if (e instanceof RushApiError && e.code === 'student_required' && Array.isArray(e.body.candidates)) {
          setCandidates(e.body.candidates as SchoolStudent[]);
        }
      });
    return () => { live = false; };
  }, [auth, mode, period, scope, schoolPeriod, studentId, needsSignIn, queryKey]);

  // Week ↔ daily/weekly: keep the closest window when crossing board families.
  const changeScope = (s: BoardScope) => {
    if (isSchool(s) && !school) setSchoolPeriod(period === 'all' ? 'all' : 'week');
    if (!isSchool(s) && school) setPeriod(schoolPeriod === 'all' ? 'all' : 'weekly');
    setPickedScope(s);
  };

  const studentRequired = error?.code === 'student_required';
  const pickStudent = (
    <StudentPicker
      students={known}
      value={studentId ?? (status === 'ready' ? loaded!.schoolBoard?.student_id ?? null : null)}
      label={t('pickStudent')}
      fallbackName={t('student')}
      onChange={setStudentId}
    />
  );

  const note = (text: ReactNode) => (
    <div className={styles.lbList}>
      <p className={styles.lbEmpty}>{text}</p>
    </div>
  );

  let list: ReactNode;
  if (needsSignIn) {
    list = note(<a className={styles.linkButton} href={signInHref}>{t('signIn')}</a>);
  } else if (status === 'loading') {
    list = note(t('loading'));
  } else if (status === 'error') {
    if (!school || !error) list = note(t('error'));
    else if (error.status === 401) list = note(<a className={styles.linkButton} href={signInHref}>{t('schoolSignIn')}</a>);
    else if (studentRequired) {
      list = (
        <div className={styles.lbList}>
          <div className={styles.lbPick}>
            <p className={styles.lbPickLabel}>{t('pickStudent')}</p>
            {pickStudent}
          </div>
        </div>
      );
    } else if (error.status === 403) list = note(t('notLinked'));
    else if (error.status >= 500) list = note(t('unavailable'));
    else list = note(t('error'));
  } else if (school) {
    const { entries, me } = loaded!.schoolBoard!;
    const pinned = me && !entries.some((e) => e.is_self) ? me : null;
    list = (
      <ol className={styles.lbList}>
        {pinned && (
          <li className={`${styles.lbRow} ${styles.lbMine}`} data-testid="lb-me">
            <Rank n={pinned.rank} />
            <span className={styles.lbName}>{t('you')}</span>
            <span className={styles.lbScore}>{pinned.score}</span>
          </li>
        )}
        {entries.length === 0 && <li className={styles.lbEmpty}>{t('empty')}</li>}
        {entries.map((e, i) => (
          <li
            key={`${e.rank}-${i}`}
            className={`${styles.lbRow} ${e.is_self ? styles.lbMine : ''} ${pinned && i === 0 ? styles.lbDivider : ''}`}
            data-self={e.is_self || undefined}
          >
            <Rank n={e.rank} />
            <span className={styles.lbName}>
              <span className={styles.lbLine}>{e.name || t('student')}</span>
              {scope === 'school' && e.branch_name && (
                <span className={`${styles.lbLine} ${styles.lbSub}`}>{e.branch_name}</span>
              )}
            </span>
            <span className={styles.lbScore}>{e.score}</span>
          </li>
        ))}
      </ol>
    );
  } else {
    const entries = loaded!.board!.entries ?? [];
    const me = scope === 'global' ? loaded!.board!.me : null;
    list = (
      <ol className={styles.lbList}>
        {me && (
          <li className={`${styles.lbRow} ${styles.lbMine}`} data-testid="lb-me">
            <Rank n={me.rank} />
            <span className={styles.lbName}>{t('you')}</span>
            <span className={styles.lbScore}>{me.score}</span>
          </li>
        )}
        {entries.length === 0 && <li className={styles.lbEmpty}>{t('empty')}</li>}
        {entries.map((e, i) => {
          const mine = scope === 'global' && userId !== null && e.user_id === userId;
          return (
            <li
              key={e.run_id}
              className={`${styles.lbRow} ${mine ? styles.lbMine : ''} ${me && i === 0 ? styles.lbDivider : ''}`}
            >
              <Rank n={e.rank} />
              <span className={styles.lbName}>
                {scope === 'personal'
                  ? new Date(e.ended_at).toLocaleDateString()
                  : e.display_name || t('player')}
              </span>
              <span className={styles.lbScore}>{e.score}</span>
            </li>
          );
        })}
      </ol>
    );
  }

  return (
    <div data-testid="rush-leaderboard">
      <div className={styles.segRow}>
        <Seg value={scope} options={scopes} label={(s) => t(s)} onChange={changeScope} />
        {school
          ? <Seg value={schoolPeriod} options={SCHOOL_PERIODS} label={(p) => t(p)} onChange={setSchoolPeriod} />
          : <Seg value={period} options={PERIODS} label={(p) => t(p)} onChange={setPeriod} />}
      </div>
      {school && known.length > 1 && !studentRequired && <div className={styles.lbStudents}>{pickStudent}</div>}
      {list}
    </div>
  );
}
