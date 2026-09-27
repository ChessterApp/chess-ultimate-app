/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { act, renderHook } from '@testing-library/react';

import useOnScreenKeyboard from '../useOnScreenKeyboard';

// A phone: 844px layout viewport; the visual viewport shrinks with the keyboard.
class FakeVisualViewport extends EventTarget {
  height = 844;
  offsetTop = 0;
  scale = 1;
}

let vv: FakeVisualViewport;
let field: HTMLTextAreaElement;

beforeEach(() => {
  vv = new FakeVisualViewport();
  Object.defineProperty(window, 'visualViewport', { configurable: true, value: vv });
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: 844 });
  field = document.createElement('textarea');
  document.body.appendChild(field);
});

afterEach(() => {
  field.remove();
});

function keyboardUp(height = 470, offsetTop = 0) {
  vv.height = height;
  vv.offsetTop = offsetTop;
  vv.dispatchEvent(new Event('resize'));
}

describe('useOnScreenKeyboard', () => {
  it('reports the keyboard and the visible area when a field is focused and the view shrinks', () => {
    const { result } = renderHook(() => useOnScreenKeyboard());
    expect(result.current.open).toBe(false);

    act(() => {
      field.focus();
      keyboardUp(470, 12);
    });
    expect(result.current).toEqual({ open: true, height: 470, top: 12 });

    act(() => {
      field.blur();
      keyboardUp(844, 0);
    });
    expect(result.current.open).toBe(false);
  });

  it('ignores a shrink without a focused field (toolbars, split view)', () => {
    const { result } = renderHook(() => useOnScreenKeyboard());
    act(() => keyboardUp(470));
    expect(result.current.open).toBe(false);
  });

  it('ignores pinch-zoom and small toolbar changes', () => {
    const { result } = renderHook(() => useOnScreenKeyboard());
    act(() => {
      field.focus();
      vv.scale = 2;
      keyboardUp(422);
    });
    expect(result.current.open).toBe(false);

    act(() => {
      vv.scale = 1;
      keyboardUp(780); // the browser's bottom toolbar, not a keyboard
    });
    expect(result.current.open).toBe(false);
  });
});
