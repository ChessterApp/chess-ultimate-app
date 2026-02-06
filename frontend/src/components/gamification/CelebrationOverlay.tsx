'use client';

import { useEffect, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { ChessterMascot } from '../mascot/ChessterMascot';

type CelebrationType = 'levelUp' | 'achievement' | 'streak' | 'lessonComplete' | 'courseComplete';

interface CelebrationOverlayProps {
  type: CelebrationType;
  title: string;
  subtitle?: string;
  icon?: string;
  xpGained?: number;
  onClose: () => void;
  autoClose?: boolean;
  autoCloseDelay?: number;
}

export function CelebrationOverlay({
  type,
  title,
  subtitle,
  icon,
  xpGained,
  onClose,
  autoClose = true,
  autoCloseDelay = 4000,
}: CelebrationOverlayProps) {
  const [isVisible, setIsVisible] = useState(false);
  const [confetti, setConfetti] = useState<{ id: number; x: number; delay: number; color: string }[]>([]);
  const t = useTranslations('gamification');

  const generateConfetti = useCallback(() => {
    const colors = ['#8B5CF6', '#22C55E', '#F59E0B', '#EF4444', '#3B82F6', '#EC4899'];
    const pieces = Array.from({ length: 50 }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      delay: Math.random() * 0.5,
      color: colors[Math.floor(Math.random() * colors.length)],
    }));
    setConfetti(pieces);
  }, []);

  useEffect(() => {
    setIsVisible(true);
    generateConfetti();

    if (autoClose) {
      const timer = setTimeout(() => {
        setIsVisible(false);
        setTimeout(onClose, 300);
      }, autoCloseDelay);
      return () => clearTimeout(timer);
    }
  }, [autoClose, autoCloseDelay, onClose, generateConfetti]);

  const handleClose = () => {
    setIsVisible(false);
    setTimeout(onClose, 300);
  };

  const typeConfig: Record<CelebrationType, { bg: string; iconDefault: string; mascotMood: 'celebrating' | 'happy' }> = {
    levelUp: {
      bg: 'from-purple-500 to-purple-700',
      iconDefault: '🎉',
      mascotMood: 'celebrating',
    },
    achievement: {
      bg: 'from-amber-500 to-orange-600',
      iconDefault: '🏆',
      mascotMood: 'celebrating',
    },
    streak: {
      bg: 'from-orange-500 to-red-500',
      iconDefault: '🔥',
      mascotMood: 'celebrating',
    },
    lessonComplete: {
      bg: 'from-green-500 to-emerald-600',
      iconDefault: '✅',
      mascotMood: 'happy',
    },
    courseComplete: {
      bg: 'from-blue-500 to-indigo-600',
      iconDefault: '🎓',
      mascotMood: 'celebrating',
    },
  };

  const config = typeConfig[type];

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center transition-opacity duration-300 ${
        isVisible ? 'opacity-100' : 'opacity-0 pointer-events-none'
      }`}
      onClick={handleClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      {/* Confetti */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        {confetti.map((piece) => (
          <div
            key={piece.id}
            className="absolute w-3 h-3 animate-confetti"
            style={{
              left: `${piece.x}%`,
              backgroundColor: piece.color,
              animationDelay: `${piece.delay}s`,
              borderRadius: Math.random() > 0.5 ? '50%' : '0',
              transform: `rotate(${Math.random() * 360}deg)`,
            }}
          />
        ))}
      </div>

      {/* Content */}
      <div
        className={`relative bg-gradient-to-br ${config.bg} rounded-3xl p-8 mx-4 max-w-sm w-full text-center text-white shadow-2xl transform transition-all duration-300 ${
          isVisible ? 'scale-100 translate-y-0' : 'scale-90 translate-y-4'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close button */}
        <button
          onClick={handleClose}
          className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-full bg-white/20 hover:bg-white/30 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        {/* Icon */}
        <div className="text-6xl mb-4 animate-bounce">{icon || config.iconDefault}</div>

        {/* Title */}
        <h2 className="text-2xl font-bold mb-2">{title}</h2>

        {/* Subtitle */}
        {subtitle && <p className="text-white/80 mb-4">{subtitle}</p>}

        {/* XP Gained */}
        {xpGained && xpGained > 0 && (
          <div className="inline-flex items-center gap-2 bg-white/20 rounded-full px-4 py-2 mb-4">
            <svg className="w-5 h-5 text-amber-300" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" />
            </svg>
            <span className="font-bold">+{xpGained} {t('xp')}</span>
          </div>
        )}

        {/* Mascot */}
        <div className="flex justify-center mt-4">
          <ChessterMascot mood={config.mascotMood} size="lg" animate />
        </div>

        {/* Continue button */}
        <button
          onClick={handleClose}
          className="mt-6 w-full bg-white text-gray-900 font-semibold py-3 px-6 rounded-xl hover:bg-gray-100 active:scale-98 transition-all"
        >
          {t('celebration.keepGoing')}
        </button>
      </div>
    </div>
  );
}

// Quick celebration for smaller achievements
interface QuickCelebrationProps {
  message: string;
  icon?: string;
  xp?: number;
  onComplete?: () => void;
}

export function QuickCelebration({ message, icon = '🎉', xp, onComplete }: QuickCelebrationProps) {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => {
      setVisible(false);
      onComplete?.();
    }, 2000);
    return () => clearTimeout(timer);
  }, [onComplete]);

  if (!visible) return null;

  return (
    <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 animate-slideDown">
      <div className="flex items-center gap-3 bg-white rounded-full px-5 py-3 shadow-lg border border-gray-100">
        <span className="text-2xl">{icon}</span>
        <span className="font-medium text-gray-800">{message}</span>
        {xp && xp > 0 && (
          <span className="flex items-center gap-1 text-amber-500 font-bold">
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" />
            </svg>
            +{xp}
          </span>
        )}
      </div>
    </div>
  );
}

// Level up specific celebration
interface LevelUpCelebrationProps {
  newLevel: string;
  levelIcon: string;
  xpGained: number;
  onClose: () => void;
}

export function LevelUpCelebration({ newLevel, levelIcon, xpGained, onClose }: LevelUpCelebrationProps) {
  const t = useTranslations('gamification');

  return (
    <CelebrationOverlay
      type="levelUp"
      title={t('celebration.levelUp')}
      subtitle={`${t('celebration.greatJob')} ${newLevel}!`}
      icon={levelIcon}
      xpGained={xpGained}
      onClose={onClose}
      autoClose={false}
    />
  );
}

// Streak celebration
interface StreakCelebrationProps {
  days: number;
  onClose: () => void;
}

export function StreakCelebration({ days, onClose }: StreakCelebrationProps) {
  const t = useTranslations('gamification');
  const milestones = [7, 30, 100, 365];
  const isMilestone = milestones.includes(days);

  return (
    <CelebrationOverlay
      type="streak"
      title={isMilestone ? `${days} ${t('dayStreak')}!` : t('keepItGoing')}
      subtitle={
        isMilestone
          ? `${t('celebration.amazing')} ${days} ${t('dayStreak')}!`
          : `${days} ${t('dayStreak')}! ${t('keepItGoing')}`
      }
      icon="🔥"
      onClose={onClose}
      autoClose={!isMilestone}
      autoCloseDelay={isMilestone ? 6000 : 3000}
    />
  );
}

// Achievement unlocked celebration
interface AchievementCelebrationProps {
  name: string;
  description: string;
  icon?: string;
  xpReward: number;
  onClose: () => void;
}

export function AchievementCelebration({
  name,
  description,
  icon = '🏆',
  xpReward,
  onClose,
}: AchievementCelebrationProps) {
  const t = useTranslations('gamification');

  return (
    <CelebrationOverlay
      type="achievement"
      title={t('celebration.achievementUnlocked')}
      subtitle={`${name}: ${description}`}
      icon={icon}
      xpGained={xpReward}
      onClose={onClose}
      autoClose={false}
    />
  );
}
