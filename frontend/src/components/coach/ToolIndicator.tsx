'use client';

import React from 'react';

interface ToolIndicatorProps {
  toolName: string;
  visible: boolean;
}

export default function ToolIndicator({ toolName, visible }: ToolIndicatorProps) {
  if (!visible) return null;

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 bg-white/5 rounded-lg text-sm text-gray-400 animate-pulse">
      <svg
        className="animate-spin h-4 w-4"
        viewBox="0 0 24 24"
        fill="none"
      >
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
        />
      </svg>
      <span>{toolName}</span>
    </div>
  );
}
