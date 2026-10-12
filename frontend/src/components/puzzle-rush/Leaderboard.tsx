'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { rushApi, type RushAuth } from '@/lib/puzzle-rush/api';
import type { LeaderboardResponse, RushMode, RushPeriod, RushScope } from '@/lib/puzzle-rush/types';
import styles from './PuzzleRush.module.css';

const PERIODS: RushPeriod[] = ['daily', 'weekly', 'all'];
const SCOPES: RushScope[] = ['global', 'personal'];
const MEDAL = [styles.rankGold, styles.rankSilver, styles.rankBronze];

interface Props {
  mode: RushMode;
  auth: () => RushAuth;
  isGuest: boolean;
  userId: string | null;
  signInHref: string;
  /** Bump to refetch (e.g. after a run ends). */
  refreshKey?: string;
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

/** S11: Global | Personal × Daily | Weekly | All-time, own row pinned first. */
export default function Leaderboard({ mode, auth, isGuest, userId, signInHref, refreshKey = '' }: Props) {
  const t = useTranslations('puzzleRush.leaderboard');
  const [scope, setScope] = useState<RushScope>('global');
  const [period, setPeriod] = useState<RushPeriod>('daily');
  const needsSignIn = scope === 'personal' && isGuest;
  // Each response is tagged with the query it answers; anything else is "loading".
  const queryKey = `${mode}|${period}|${scope}|${isGuest}|${refreshKey}`;
  const [loaded, setLoaded] = useState<{ key: string; data: LeaderboardResponse | null } | null>(null);
  const status = loaded?.key !== queryKey ? 'loading' : loaded.data ? 'ready' : 'error';
  const data = status === 'ready' ? loaded!.data : null;

  useEffect(() => {
    if (needsSignIn) return;
    let live = true;
    rushApi.leaderboard(auth(), mode, period, scope)
      .then((d) => { if (live) setLoaded({ key: queryKey, data: d }); })
      .catch(() => { if (live) setLoaded({ key: queryKey, data: null }); });
    return () => { live = false; };
  }, [auth, mode, period, scope, needsSignIn, queryKey]);

  const entries = data?.entries ?? [];
  const me = scope === 'global' ? data?.me : null;

  return (
    <div data-testid="rush-leaderboard">
      <div className={styles.segRow}>
        <Seg value={scope} options={SCOPES} label={(s) => t(s)} onChange={setScope} />
        <Seg value={period} options={PERIODS} label={(p) => t(p)} onChange={setPeriod} />
      </div>

      {needsSignIn ? (
        <div className={styles.lbList}>
          <p className={styles.lbEmpty}>
            <a className={styles.linkButton} href={signInHref}>{t('signIn')}</a>
          </p>
        </div>
      ) : status !== 'ready' ? (
        <div className={styles.lbList}>
          <p className={styles.lbEmpty}>{status === 'loading' ? t('loading') : t('error')}</p>
        </div>
      ) : (
        <ol className={styles.lbList}>
          {me && (
            <li className={`${styles.lbRow} ${styles.lbMine}`} data-testid="lb-me">
              <span className={`${styles.rank} ${me.rank <= 3 ? MEDAL[me.rank - 1] : ''}`}>#{me.rank}</span>
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
                <span className={`${styles.rank} ${e.rank <= 3 ? MEDAL[e.rank - 1] : ''}`}>#{e.rank}</span>
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
      )}
    </div>
  );
}
