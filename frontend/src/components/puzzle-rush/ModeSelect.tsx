'use client';

import { useTranslations } from 'next-intl';
import { RUSH_MODES, type BestsResponse, type RushMode } from '@/lib/puzzle-rush/types';
import styles from './PuzzleRush.module.css';

const MODE_ICON: Record<RushMode, { glyph: string; tone: string }> = {
  '3min': { glyph: '⚡', tone: styles.iconAmber },
  '5min': { glyph: '⏱️', tone: styles.iconGreen },
  survival: { glyph: '♾️', tone: styles.iconAccent },
};

interface Props {
  selected: RushMode;
  bests: BestsResponse | null;
  onSelect: (mode: RushMode) => void;
  disabled?: boolean;
}

/** S1 mode cards: 3 min / 5 min / Survival, each with Top Score + Best Today. */
export default function ModeSelect({ selected, bests, onSelect, disabled = false }: Props) {
  const t = useTranslations('puzzleRush');
  return (
    <div className={styles.modes} role="radiogroup" aria-label={t('tabs.play')}>
      {RUSH_MODES.map((mode) => {
        const b = bests?.[mode];
        const active = mode === selected;
        return (
          <button
            key={mode}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled}
            className={`${styles.mode} ${active ? styles.modeActive : ''}`}
            onClick={() => onSelect(mode)}
            data-mode={mode}
          >
            <span className={`${styles.modeIcon} ${MODE_ICON[mode].tone}`} aria-hidden="true">
              {MODE_ICON[mode].glyph}
            </span>
            <span className={styles.modeText}>
              <span className={styles.modeTitle}>{t(`modes.${mode}.title`)}</span>
              <span className={styles.modeDesc}>{t(`modes.${mode}.desc`)}</span>
            </span>
            <span className={styles.modeStats}>
              <span className={styles.bestPill} title={t('topScore')}>
                {t('best', { score: b?.top_score ?? '--' })}
              </span>
              <span className={styles.todayLine} title={t('bestToday')}>
                {t('today', { score: b?.best_today ?? '--' })}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
