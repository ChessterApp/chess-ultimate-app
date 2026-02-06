'use client';

import { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';

interface XPDisplayProps {
  xp: number;
  previousXp?: number;
  showAnimation?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export function XPDisplay({ xp, previousXp, showAnimation = false, size = 'md' }: XPDisplayProps) {
  const [displayXp, setDisplayXp] = useState(previousXp ?? xp);
  const [isAnimating, setIsAnimating] = useState(false);
  const t = useTranslations('gamification');

  useEffect(() => {
    if (showAnimation && previousXp !== undefined && previousXp !== xp) {
      setIsAnimating(true);
      const diff = xp - previousXp;
      const duration = 1000;
      const steps = 20;
      const increment = diff / steps;
      let current = previousXp;
      let step = 0;

      const interval = setInterval(() => {
        step++;
        current += increment;
        setDisplayXp(Math.round(current));

        if (step >= steps) {
          clearInterval(interval);
          setDisplayXp(xp);
          setTimeout(() => setIsAnimating(false), 300);
        }
      }, duration / steps);

      return () => clearInterval(interval);
    } else {
      setDisplayXp(xp);
    }
  }, [xp, previousXp, showAnimation]);

  const sizeClasses = {
    sm: 'text-sm gap-1',
    md: 'text-base gap-1.5',
    lg: 'text-lg gap-2',
  };

  const iconSizes = {
    sm: 'w-4 h-4',
    md: 'w-5 h-5',
    lg: 'w-6 h-6',
  };

  return (
    <div
      className={`flex items-center ${sizeClasses[size]} font-semibold text-amber-500 ${
        isAnimating ? 'animate-pulse scale-110' : ''
      } transition-transform duration-200`}
    >
      <svg
        className={iconSizes[size]}
        viewBox="0 0 24 24"
        fill="currentColor"
      >
        <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" />
      </svg>
      <span className={isAnimating ? 'text-amber-400' : ''}>
        {displayXp.toLocaleString()} {t('xp')}
      </span>
    </div>
  );
}

interface XPGainProps {
  amount: number;
  onComplete?: () => void;
}

export function XPGain({ amount, onComplete }: XPGainProps) {
  const [visible, setVisible] = useState(true);
  const t = useTranslations('gamification');

  useEffect(() => {
    const timer = setTimeout(() => {
      setVisible(false);
      onComplete?.();
    }, 1500);
    return () => clearTimeout(timer);
  }, [onComplete]);

  if (!visible) return null;

  return (
    <div className="fixed top-20 left-1/2 -translate-x-1/2 z-50 animate-bounce">
      <div className="bg-amber-500 text-white px-4 py-2 rounded-full font-bold text-lg shadow-lg flex items-center gap-2">
        <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" />
        </svg>
        +{amount} {t('xp')}
      </div>
    </div>
  );
}
