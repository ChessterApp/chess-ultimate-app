'use client';

interface LeagueBadgeProps {
  league: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const LEAGUE_CONFIG: Record<string, { label: string; color: string; bg: string; icon: string }> = {
  C: {
    label: 'League C',
    color: 'text-gray-700 dark:text-gray-300',
    bg: 'bg-gray-100 dark:bg-gray-700',
    icon: '\u2659',
  },
  B: {
    label: 'League B',
    color: 'text-blue-700 dark:text-blue-300',
    bg: 'bg-blue-100 dark:bg-blue-900/30',
    icon: '\u2658',
  },
  A: {
    label: 'League A',
    color: 'text-purple-700 dark:text-purple-300',
    bg: 'bg-purple-100 dark:bg-purple-900/30',
    icon: '\u2657',
  },
  Master: {
    label: 'Master',
    color: 'text-yellow-700 dark:text-yellow-300',
    bg: 'bg-yellow-100 dark:bg-yellow-900/30',
    icon: '\u2655',
  },
};

const SIZES = {
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-3 py-1 text-sm',
  lg: 'px-4 py-1.5 text-base',
};

export default function LeagueBadge({ league, size = 'sm', className = '' }: LeagueBadgeProps) {
  const config = LEAGUE_CONFIG[league] || LEAGUE_CONFIG.C;
  const sizeClass = SIZES[size];

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-medium ${config.bg} ${config.color} ${sizeClass} ${className}`}>
      <span>{config.icon}</span>
      <span>{config.label}</span>
    </span>
  );
}
