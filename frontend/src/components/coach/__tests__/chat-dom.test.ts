/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from 'vitest';
import { fitTextarea, isNearBottom, shouldSendOnEnter, STICK_THRESHOLD_PX } from '../chat-dom';

describe('isNearBottom', () => {
  const at = (scrollTop: number) => ({ scrollTop, scrollHeight: 1000, clientHeight: 400 });

  it('is true at the very bottom', () => {
    expect(isNearBottom(at(600))).toBe(true);
  });

  it('is true within the threshold', () => {
    expect(isNearBottom(at(600 - STICK_THRESHOLD_PX))).toBe(true);
  });

  it('is false once scrolled up past the threshold', () => {
    expect(isNearBottom(at(600 - STICK_THRESHOLD_PX - 1))).toBe(false);
    expect(isNearBottom(at(0))).toBe(false);
  });

  it('is true when the content does not overflow', () => {
    expect(isNearBottom({ scrollTop: 0, scrollHeight: 300, clientHeight: 400 })).toBe(true);
  });
});

describe('shouldSendOnEnter', () => {
  const key = (k: string, shiftKey = false, isComposing = false) => ({ key: k, shiftKey, isComposing });

  it('sends on Enter with a fine pointer', () => {
    expect(shouldSendOnEnter(key('Enter'), false)).toBe(true);
  });

  it('inserts a newline on Shift+Enter', () => {
    expect(shouldSendOnEnter(key('Enter', true), false)).toBe(false);
  });

  it('does not send while an IME is composing', () => {
    expect(shouldSendOnEnter(key('Enter', false, true), false)).toBe(false);
  });

  it('leaves Enter as a newline on touch keyboards', () => {
    expect(shouldSendOnEnter(key('Enter'), true)).toBe(false);
  });

  it('ignores other keys', () => {
    expect(shouldSendOnEnter(key('a'), false)).toBe(false);
  });
});

describe('fitTextarea', () => {
  function textarea(scrollHeight: number) {
    const el = document.createElement('textarea');
    el.style.lineHeight = '20px';
    el.style.paddingTop = '8px';
    el.style.paddingBottom = '8px';
    el.style.borderTopWidth = '1px';
    el.style.borderBottomWidth = '1px';
    Object.defineProperty(el, 'scrollHeight', { get: () => scrollHeight });
    return el;
  }

  it('grows with the content', () => {
    const el = textarea(56); // 2 lines + padding
    fitTextarea(el);
    expect(el.style.height).toBe('58px');
    expect(el.style.overflowY).toBe('hidden');
  });

  it('stops at 5 lines and scrolls beyond', () => {
    const el = textarea(400);
    fitTextarea(el);
    expect(el.style.height).toBe(`${20 * 5 + 16 + 2}px`);
    expect(el.style.overflowY).toBe('auto');
  });
});
