'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';

interface StreakBannerProps {
  streakDays: number;
  lastActivityDate?: string;
  showCalendar?: boolean;
}

export function StreakBanner({ streakDays, lastActivityDate, showCalendar = false }: StreakBannerProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const t = useTranslations('gamification');

  const isActiveToday = lastActivityDate
    ? new Date(lastActivityDate).toDateString() === new Date().toDateString()
    : false;

  const getWeekDays = () => {
    const days = [];
    const today = new Date();
    const startOfWeek = new Date(today);
    startOfWeek.setDate(today.getDate() - today.getDay() + 1); // Monday

    for (let i = 0; i < 7; i++) {
      const day = new Date(startOfWeek);
      day.setDate(startOfWeek.getDate() + i);
      days.push({
        label: [t('weekdays.mon'), t('weekdays.tue'), t('weekdays.wed'), t('weekdays.thu'), t('weekdays.fri'), t('weekdays.sat'), t('weekdays.sun')][i],
        date: day,
        isPast: day < today && day.toDateString() !== today.toDateString(),
        isToday: day.toDateString() === today.toDateString(),
        isCompleted: day <= today && streakDays > 0 &&
          (today.getTime() - day.getTime()) / (1000 * 60 * 60 * 24) < streakDays,
      });
    }
    return days;
  };

  return (
    <div className="bg-gradient-to-r from-orange-500 to-amber-500 rounded-2xl p-4 text-white shadow-lg">
      <button
        onClick={() => showCalendar && setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <div className={`text-3xl ${streakDays > 0 ? 'animate-pulse' : 'opacity-50'}`}>
            🔥
          </div>
          <div className="text-left">
            <div className="text-2xl font-bold">{streakDays} {t('dayStreak')}!</div>
            <div className="text-sm text-orange-100">
              {isActiveToday ? t('streakProtected') : t('practiceToKeepStreak')}
            </div>
          </div>
        </div>
        {showCalendar && (
          <svg
            className={`w-6 h-6 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        )}
      </button>

      {isExpanded && showCalendar && (
        <div className="mt-4 pt-4 border-t border-orange-400">
          <div className="text-sm text-orange-100 mb-2">{t('thisWeek')}</div>
          <div className="flex justify-between">
            {getWeekDays().map((day, i) => (
              <div key={i} className="flex flex-col items-center gap-1">
                <span className="text-xs text-orange-200">{day.label}</span>
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                    day.isCompleted
                      ? 'bg-white text-orange-500'
                      : day.isToday
                      ? 'bg-orange-400 text-white ring-2 ring-white'
                      : 'bg-orange-600/50 text-orange-200'
                  }`}
                >
                  {day.isCompleted ? '✓' : day.date.getDate()}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function StreakMini({ streakDays }: { streakDays: number }) {
  return (
    <div className="flex items-center gap-1.5 text-orange-500 font-semibold">
      <span className={streakDays > 0 ? '' : 'grayscale opacity-50'}>🔥</span>
      <span>{streakDays}</span>
    </div>
  );
}
