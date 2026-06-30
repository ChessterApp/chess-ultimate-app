'use client';

import { ReactNode } from 'react';
import { useBranding } from '@/contexts/OrganizationContext';
import { ChessterMascot } from './ChessterMascot';

type MascotMood = 'happy' | 'thinking' | 'celebrating' | 'sad' | 'encouraging' | 'neutral';

interface SpeechBubbleProps {
  children: ReactNode;
  mood?: MascotMood;
  position?: 'left' | 'right' | 'top' | 'bottom';
  showMascot?: boolean;
  mascotSize?: 'sm' | 'md' | 'lg';
  className?: string;
}

export function SpeechBubble({
  children,
  mood = 'neutral',
  position = 'left',
  showMascot = true,
  mascotSize = 'md',
  className = '',
}: SpeechBubbleProps) {
  const isHorizontal = position === 'left' || position === 'right';

  const bubbleClasses = {
    left: 'ml-3',
    right: 'mr-3 order-first',
    top: 'mt-3',
    bottom: 'mb-3 order-first',
  };

  const arrowClasses = {
    left: 'left-0 top-1/2 -translate-x-full -translate-y-1/2 border-r-white border-r-8 border-y-8 border-y-transparent border-l-0',
    right: 'right-0 top-1/2 translate-x-full -translate-y-1/2 border-l-white border-l-8 border-y-8 border-y-transparent border-r-0',
    top: 'top-0 left-1/2 -translate-y-full -translate-x-1/2 border-b-white border-b-8 border-x-8 border-x-transparent border-t-0',
    bottom: 'bottom-0 left-1/2 translate-y-full -translate-x-1/2 border-t-white border-t-8 border-x-8 border-x-transparent border-b-0',
  };

  return (
    <div
      className={`flex ${isHorizontal ? 'flex-row' : 'flex-col'} items-center ${className}`}
    >
      {showMascot && <ChessterMascot mood={mood} size={mascotSize} />}

      <div className={`relative ${bubbleClasses[position]}`}>
        {/* Arrow pointer */}
        <div className={`absolute w-0 h-0 ${arrowClasses[position]}`} />

        {/* Bubble content */}
        <div className="bg-white rounded-2xl px-4 py-3 shadow-lg border border-gray-100 max-w-xs">
          <div className="text-gray-700 text-sm leading-relaxed">{children}</div>
        </div>
      </div>
    </div>
  );
}

// Pre-built message types for common scenarios
interface QuickMessageProps {
  type: 'correct' | 'incorrect' | 'hint' | 'encouragement' | 'welcome' | 'streak' | 'levelUp';
  customMessage?: string;
  details?: string;
}

const defaultMessages: Record<QuickMessageProps['type'], { text: string; mood: MascotMood }> = {
  correct: { text: "Great job! That's the right move!", mood: 'celebrating' },
  incorrect: { text: "Not quite! Let's try again.", mood: 'encouraging' },
  hint: { text: 'Here\'s a hint: Look at the center of the board.', mood: 'thinking' },
  encouragement: { text: "You're doing great! Keep going!", mood: 'encouraging' },
  welcome: { text: "Welcome back! Ready to learn some chess?", mood: 'happy' },
  streak: { text: "Amazing! You're on fire! 🔥", mood: 'celebrating' },
  levelUp: { text: "Congratulations! You've leveled up! 🎉", mood: 'celebrating' },
};

export function QuickMessage({ type, customMessage, details }: QuickMessageProps) {
  const { text, mood } = defaultMessages[type];

  return (
    <SpeechBubble mood={mood}>
      <p className="font-medium">{customMessage || text}</p>
      {details && <p className="text-gray-500 text-xs mt-1">{details}</p>}
    </SpeechBubble>
  );
}

// Floating mascot tip that appears temporarily
interface FloatingTipProps {
  message: string;
  mood?: MascotMood;
  duration?: number;
  onDismiss?: () => void;
  position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
}

export function FloatingTip({
  message,
  mood = 'happy',
  duration = 5000,
  onDismiss,
  position = 'bottom-right',
}: FloatingTipProps) {
  const positionClasses = {
    'top-left': 'top-4 left-4',
    'top-right': 'top-4 right-4',
    'bottom-left': 'bottom-20 left-4', // Account for bottom nav
    'bottom-right': 'bottom-20 right-4',
  };

  return (
    <div
      className={`fixed ${positionClasses[position]} z-40 animate-fadeIn`}
      style={{
        animation: `fadeIn 0.3s ease-out, fadeOut 0.3s ease-in ${duration - 300}ms forwards`,
      }}
    >
      <div className="relative">
        <button
          onClick={onDismiss}
          className="absolute -top-2 -right-2 w-6 h-6 bg-gray-200 rounded-full flex items-center justify-center text-gray-500 hover:bg-gray-300 transition-colors z-10"
        >
          ×
        </button>
        <SpeechBubble mood={mood} position="left" mascotSize="sm">
          {message}
        </SpeechBubble>
      </div>
    </div>
  );
}

// Inline tip for lesson content
interface InlineTipProps {
  message: string;
  mood?: MascotMood;
  variant?: 'default' | 'compact' | 'highlight';
}

export function InlineTip({ message, mood = 'thinking', variant = 'default' }: InlineTipProps) {
  const branding = useBranding();
  if (variant === 'compact') {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-600 bg-gray-50 rounded-lg px-3 py-2">
        <img
          src={branding.logoUrl || '/static/images/chesster-logo-v3.png'}
          alt={branding.name}
          className="w-6 h-6"
        />
        <span>{message}</span>
      </div>
    );
  }

  if (variant === 'highlight') {
    return (
      <div className="bg-purple-50 border-l-4 border-purple-500 rounded-r-lg p-4">
        <SpeechBubble mood={mood} mascotSize="sm">
          {message}
        </SpeechBubble>
      </div>
    );
  }

  return (
    <div className="my-4">
      <SpeechBubble mood={mood}>{message}</SpeechBubble>
    </div>
  );
}
