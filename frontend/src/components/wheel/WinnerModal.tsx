'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import type { WheelSegment } from '@/lib/wheel/types';

interface WinnerModalProps {
  segment: WheelSegment;
  onClose: () => void;
  onSpinAgain: () => void;
}

export default function WinnerModal({ segment, onClose, onSpinAgain }: WinnerModalProps) {
  const t = useTranslations('wheel');

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t('winnerTitle')}
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-3xl bg-gradient-to-b from-[#fff7e6] to-[#f3d98a] p-8 text-center shadow-2xl"
        style={{ border: '4px solid #a9782b' }}
        onClick={(e) => e.stopPropagation()}
      >
        <p className="text-sm font-semibold uppercase tracking-widest text-[#a9782b]">
          {t('winnerTitle')}
        </p>
        {segment.emoji && <div className="mt-3 text-6xl leading-none">{segment.emoji}</div>}
        <h2 className="mt-3 break-words text-3xl font-extrabold text-[#231007]">
          {segment.label || t('emptyLabel')}
        </h2>
        <div className="mt-6 flex flex-col gap-2">
          <button
            type="button"
            onClick={onSpinAgain}
            className="rounded-full bg-[#c62828] py-3 font-bold text-white transition-colors hover:bg-[#a71d1d]"
          >
            {t('spinAgain')}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full py-2 text-sm font-semibold text-[#a9782b] hover:text-[#8a6220]"
          >
            {t('close')}
          </button>
        </div>
      </div>
    </div>
  );
}
