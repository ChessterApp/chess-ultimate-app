/** How close (px) to the bottom still counts as "following" the conversation. */
export const STICK_THRESHOLD_PX = 80;

/** True when the scroll position is within *threshold* px of the bottom. */
export function isNearBottom(
  el: Pick<HTMLElement, 'scrollTop' | 'scrollHeight' | 'clientHeight'>,
  threshold = STICK_THRESHOLD_PX,
): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= threshold;
}

/** Enter sends; Shift+Enter, IME composition and touch keyboards insert a newline. */
export function shouldSendOnEnter(
  e: Pick<KeyboardEvent, 'key' | 'shiftKey' | 'isComposing'>,
  coarsePointer: boolean,
): boolean {
  return e.key === 'Enter' && !e.shiftKey && !e.isComposing && !coarsePointer;
}

/** Grow a textarea with its content up to *maxLines*, then let it scroll (border-box sizing). */
export function fitTextarea(el: HTMLTextAreaElement, maxLines = 5): void {
  const style = getComputedStyle(el);
  const px = (v: string) => parseFloat(v) || 0;
  const lineHeight = px(style.lineHeight) || px(style.fontSize) * 1.5 || 20;
  const border = px(style.borderTopWidth) + px(style.borderBottomWidth);
  const max = lineHeight * maxLines + px(style.paddingTop) + px(style.paddingBottom) + border;
  el.style.height = 'auto';
  const wanted = el.scrollHeight + border;
  el.style.height = `${Math.min(wanted, max)}px`;
  el.style.overflowY = wanted > max ? 'auto' : 'hidden';
}
