'use client';

import { useEffect, useRef } from 'react';

interface Props {
  open: boolean;
  onClose: () => void;
}

const shortcuts = [
  {
    category: 'Navigation',
    items: [
      { keys: ['⌘/Ctrl', '1'], desc: 'Dashboard' },
      { keys: ['⌘/Ctrl', '2'], desc: 'Courses' },
      { keys: ['⌘/Ctrl', '3'], desc: 'Puzzles' },
      { keys: ['⌘/Ctrl', '4'], desc: 'Analysis' },
      { keys: ['⌘/Ctrl', '5'], desc: 'Game Review' },
      { keys: ['⌘/Ctrl', '6'], desc: 'Settings' },
    ],
  },
  {
    category: 'Actions',
    items: [
      { keys: ['⌘/Ctrl', 'K'], desc: 'Search / Command palette' },
      { keys: ['Esc'], desc: 'Close modal / sidebar' },
    ],
  },
  {
    category: 'Chess',
    items: [
      { keys: ['←'], desc: 'Previous move' },
      { keys: ['→'], desc: 'Next move' },
      { keys: ['↑'], desc: 'First move' },
      { keys: ['↓'], desc: 'Last move' },
      { keys: ['F'], desc: 'Flip board' },
    ],
  },
  {
    category: 'General',
    items: [
      { keys: ['?'], desc: 'Show this help' },
    ],
  },
];

export default function KeyboardShortcutsHelp({ open, onClose }: Props) {
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (overlayRef.current && !overlayRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[9999] bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
      <div
        ref={overlayRef}
        className="bg-white rounded-2xl shadow-2xl max-w-lg w-full max-h-[80vh] overflow-y-auto p-6 animate-in fade-in zoom-in-95 duration-200"
      >
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-bold text-gray-900">⌨️ Keyboard Shortcuts</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors p-1"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-5">
          {shortcuts.map((group) => (
            <div key={group.category}>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                {group.category}
              </h3>
              <div className="space-y-1.5">
                {group.items.map((item, i) => (
                  <div key={i} className="flex items-center justify-between py-1">
                    <span className="text-sm text-gray-700">{item.desc}</span>
                    <div className="flex items-center gap-1">
                      {item.keys.map((k, j) => (
                        <span key={j}>
                          <kbd className="inline-block min-w-[24px] text-center px-1.5 py-0.5 text-xs font-mono bg-gray-100 text-gray-600 border border-gray-200 rounded shadow-sm">
                            {k}
                          </kbd>
                          {j < item.keys.length - 1 && (
                            <span className="text-gray-400 mx-0.5">+</span>
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-5 pt-4 border-t border-gray-100 text-center">
          <span className="text-xs text-gray-400">
            Press <kbd className="px-1 py-0.5 bg-gray-100 rounded text-gray-500 font-mono">?</kbd> to toggle this overlay
          </span>
        </div>
      </div>
    </div>
  );
}
