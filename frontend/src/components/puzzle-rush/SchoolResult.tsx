'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { rushApi, type RushAuth } from '@/lib/puzzle-rush/api';
import type { SchoolOutcome, SchoolPeriod } from '@/lib/puzzle-rush/types';
import StudentPicker from './StudentPicker';
import styles from './PuzzleRush.module.css';

interface Props {
  runId: string;
  outcome: SchoolOutcome;
  auth: () => RushAuth;
  /** Open the School tab of the leaderboard. */
  onOpenBoard: () => void;
}

type Ranks = { school: number | null; branch: number | null } | null;

/** The widest window the run beat: all-time > month > week. */
function headline(beaten: SchoolPeriod[] = []): SchoolPeriod | null {
  return (['all', 'month', 'week'] as const).find((p) => beaten.includes(p)) ?? null;
}

/**
 * Results: the survival run's Chess Empire school outcome. Families pick who
 * played (remembered pick pre-selected) before anything is pushed; a push
 * shows the new best and the student's school / branch rank this week.
 */
export default function SchoolResult({ runId, outcome: initial, auth, onOpenBoard }: Props) {
  const t = useTranslations('puzzleRush.results.school');
  const tb = useTranslations('puzzleRush.leaderboard');
  const [outcome, setOutcome] = useState(initial);
  const [dismissed, setDismissed] = useState(false);
  const [picked, setPicked] = useState<string | null>(() => {
    if (initial.status !== 'needs_student') return null;
    const last = initial.last_student_id;
    return initial.candidates.some((c) => c.student_id === last) ? last : null;
  });
  const [claiming, setClaiming] = useState(false);
  const [claimFailed, setClaimFailed] = useState(false);
  const [ranks, setRanks] = useState<Ranks>(null);

  const pushedFor = outcome.status === 'pushed' ? outcome.student_id : null;
  useEffect(() => {
    if (!pushedFor) return;
    let live = true;
    const rank = (scope: 'school' | 'branch') => rushApi.schoolLeaderboard(auth(), scope, 'week', pushedFor)
      .then((d) => d.me?.rank ?? null, () => null);
    Promise.all([rank('school'), rank('branch')]).then(([school, branch]) => {
      if (live) setRanks({ school, branch });
    });
    return () => { live = false; };
  }, [auth, pushedFor]);

  const confirm = async () => {
    if (!picked) return;
    setClaiming(true);
    setClaimFailed(false);
    try {
      setOutcome(await rushApi.schoolClaim(auth(), runId, picked));
    } catch {
      setClaimFailed(true);
    } finally {
      setClaiming(false);
    }
  };

  if (outcome.status === 'needs_student') {
    if (dismissed) return null;
    return (
      <div className={styles.school} data-testid="rush-school">
        <p className={styles.schoolTitle}>{t('whoPlayed')}</p>
        <p className={styles.schoolHint}>{t('whoPlayedHint')}</p>
        <StudentPicker
          students={outcome.candidates}
          value={picked}
          label={t('whoPlayed')}
          fallbackName={tb('student')}
          onChange={setPicked}
        />
        {claimFailed && <p className={styles.schoolError}>{t('claimError')}</p>}
        <div className={styles.schoolActions}>
          <button type="button" className={styles.ghostButton} onClick={confirm} disabled={!picked || claiming}>
            {claiming ? t('saving') : t('confirm')}
          </button>
          <button type="button" className={styles.linkButton} onClick={() => setDismissed(true)}>
            {t('skip')}
          </button>
        </div>
      </div>
    );
  }

  if (outcome.status === 'pushed') {
    const period = headline(outcome.beaten);
    const rank = (n: number | null | undefined) => (ranks === null ? '…' : n ? `#${n}` : '—');
    return (
      <div className={styles.school} data-testid="rush-school">
        {period && <p className={styles.schoolTitle}>{t('newBest', { period })}</p>}
        <ul className={`${styles.stats} ${styles.schoolStats}`}>
          <li className={styles.stat}>
            <span>{t('schoolRank')}</span>
            <b data-testid="rush-school-rank">{rank(ranks?.school)}</b>
          </li>
          <li className={styles.stat}>
            <span>{t('branchRank')}</span>
            <b data-testid="rush-branch-rank">{rank(ranks?.branch)}</b>
          </li>
        </ul>
        <button type="button" className={styles.linkButton} onClick={onOpenBoard}>
          {t('openBoard')}
        </button>
      </div>
    );
  }

  const week = outcome.status === 'not_best' ? outcome.best?.week : null;
  if (typeof week === 'number') {
    return (
      <div className={styles.school} data-testid="rush-school">
        <p className={styles.schoolHint}>{t('notBest', { score: week })}</p>
      </div>
    );
  }
  // unlinked / disabled / error / a 0-score run: nothing school-related.
  return null;
}
