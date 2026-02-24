'use client';

import { useEffect, useCallback, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';

export interface ShortcutDefinition {
  key: string;
  ctrl?: boolean;  // Ctrl/Cmd
  description: string;
  category: 'navigation' | 'actions' | 'chess' | 'general';
  action: () => void;
}

export function useKeyboardShortcuts() {
  const router = useRouter();
  const pathname = usePathname();
  const [showHelp, setShowHelp] = useState(false);

  const isInputFocused = useCallback(() => {
    const el = document.activeElement;
    if (!el) return false;
    const tag = el.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
    if ((el as HTMLElement).isContentEditable) return true;
    return false;
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      const key = e.key.toLowerCase();

      // Always handle Escape
      if (key === 'escape') {
        if (showHelp) {
          setShowHelp(false);
          e.preventDefault();
          return;
        }
        // Dispatch custom event for modals/sidebars to listen to
        window.dispatchEvent(new CustomEvent('chesster:escape'));
        return;
      }

      // Skip shortcuts when typing in inputs
      if (isInputFocused()) return;

      // ? = show help (without modifier)
      if ((key === '?' || (key === '/' && e.shiftKey)) && !mod) {
        e.preventDefault();
        setShowHelp(prev => !prev);
        return;
      }

      // Ctrl/Cmd + number = navigation
      if (mod && !e.shiftKey && !e.altKey) {
        const navMap: Record<string, string> = {
          '1': '/dashboard',
          '2': '/learn',
          '3': '/puzzle',
          '4': '/position',
          '5': '/opponent',
          '6': '/settings',
        };
        if (navMap[key]) {
          e.preventDefault();
          router.push(navMap[key]);
          return;
        }
        // Cmd+K = focus search (dispatch event)
        if (key === 'k') {
          e.preventDefault();
          window.dispatchEvent(new CustomEvent('chesster:search'));
          return;
        }
      }

      // Non-modifier shortcuts (only when not in input)
      if (!mod && !e.altKey) {
        // F = flip board
        if (key === 'f' && !e.shiftKey) {
          window.dispatchEvent(new CustomEvent('chesster:flip-board'));
          return;
        }

        // Arrow keys for move navigation on analysis/game pages
        const chessPages = ['/position', '/analyze', '/game', '/opponent', '/debut'];
        const onChessPage = chessPages.some(p => pathname?.startsWith(p));
        if (onChessPage) {
          if (key === 'arrowleft') {
            e.preventDefault();
            window.dispatchEvent(new CustomEvent('chesster:move-back'));
            return;
          }
          if (key === 'arrowright') {
            e.preventDefault();
            window.dispatchEvent(new CustomEvent('chesster:move-forward'));
            return;
          }
          if (key === 'arrowup') {
            e.preventDefault();
            window.dispatchEvent(new CustomEvent('chesster:move-first'));
            return;
          }
          if (key === 'arrowdown') {
            e.preventDefault();
            window.dispatchEvent(new CustomEvent('chesster:move-last'));
            return;
          }
        }
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [router, pathname, showHelp, isInputFocused]);

  return { showHelp, setShowHelp };
}
