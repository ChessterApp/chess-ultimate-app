'use client';

import { useEffect } from 'react';
import Image from 'next/image';
import { useTranslations } from 'next-intl';
import { LOGO_SRC } from './RunTiles';
import styles from './PuzzleRush.module.css';

/** S2: first-visit rules card. */
export default function RulesModal({ onClose }: { onClose: () => void }) {
  const t = useTranslations('puzzleRush.rules');
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className={styles.scrim} onClick={onClose}>
      <div
        className={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="rush-rules-title"
        onClick={(e) => e.stopPropagation()}
      >
        <button type="button" className={styles.closeX} onClick={onClose} aria-label={t('close')}>✕</button>
        <div className={styles.modalBody}>
          <div className={styles.brand}>
            <span className={styles.mark}>
              <Image src={LOGO_SRC} alt="" width={46} height={46} unoptimized />
            </span>
            <div>
              <h2 id="rush-rules-title" className={styles.brandTitle}>{t('title')}</h2>
              <p className={styles.brandSub}>{t('lead')}</p>
            </div>
          </div>
          <ol className={styles.rulesList}>
            {(['r1', 'r2', 'r3'] as const).map((k, i) => (
              <li key={k}>
                <span className={styles.ruleDot}>{i + 1}</span>
                <span>{t(k)}</span>
              </li>
            ))}
          </ol>
          <button type="button" className={styles.cta} onClick={onClose} autoFocus>
            {t('ok')}
          </button>
        </div>
      </div>
    </div>
  );
}
