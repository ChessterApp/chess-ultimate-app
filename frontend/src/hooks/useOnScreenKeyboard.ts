'use client';

import { useEffect, useState } from 'react';

/**
 * Whether a phone's on-screen keyboard is open, and the part of the screen it
 * leaves visible.
 *
 * iOS Safari does not shrink the page (not even `100dvh`) when the keyboard
 * opens — only `window.visualViewport` shrinks — so a full-height page keeps
 * its bottom row, where chat inputs live, under the keyboard and any fixed
 * bottom bar. A page can pin itself to `{ top, height }` while `open` is true.
 */
export interface OnScreenKeyboard {
  open: boolean;
  /** Visible height and its offset from the layout top, in CSS pixels. */
  height: number;
  top: number;
}

// Smaller gaps are browser toolbars sliding in and out, not a keyboard.
const KEYBOARD_MIN_PX = 150;

const CLOSED: OnScreenKeyboard = { open: false, height: 0, top: 0 };

function isEditable(el: Element | null): boolean {
  if (!el) return false;
  if (el instanceof HTMLTextAreaElement) return !el.readOnly && !el.disabled;
  if (el instanceof HTMLInputElement) {
    return !el.readOnly && !el.disabled && !['button', 'checkbox', 'radio', 'range', 'file', 'submit', 'reset'].includes(el.type);
  }
  return (el as HTMLElement).isContentEditable === true;
}

export function readOnScreenKeyboard(): OnScreenKeyboard {
  if (typeof window === 'undefined' || !window.visualViewport) return CLOSED;
  const vv = window.visualViewport;
  const open =
    isEditable(document.activeElement) &&
    vv.scale <= 1.01 && // pinch-zoom also shrinks the visual viewport
    window.innerHeight - vv.height > KEYBOARD_MIN_PX;
  return open ? { open, height: Math.round(vv.height), top: Math.round(vv.offsetTop) } : CLOSED;
}

export default function useOnScreenKeyboard(): OnScreenKeyboard {
  const [state, setState] = useState<OnScreenKeyboard>(CLOSED);

  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const update = () =>
      setState((prev) => {
        const next = readOnScreenKeyboard();
        return prev.open === next.open && prev.height === next.height && prev.top === next.top ? prev : next;
      });
    vv.addEventListener('resize', update);
    vv.addEventListener('scroll', update);
    // The keyboard animates after focus / before blur; the resize events above
    // carry the final size, these catch focus moving without a resize.
    document.addEventListener('focusin', update);
    document.addEventListener('focusout', update);
    update();
    return () => {
      vv.removeEventListener('resize', update);
      vv.removeEventListener('scroll', update);
      document.removeEventListener('focusin', update);
      document.removeEventListener('focusout', update);
    };
  }, []);

  return state;
}
