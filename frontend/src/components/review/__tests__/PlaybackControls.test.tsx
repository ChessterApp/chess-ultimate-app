/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { cleanup, fireEvent } from '@testing-library/react';
import PlaybackControls, { nextKeyMoment } from '../PlaybackControls';
import { renderIntl, gameReview } from './intl';

afterEach(cleanup);

describe('nextKeyMoment', () => {
  it('returns the next key moment strictly after the current ply', () => {
    expect(nextKeyMoment([5, 6, 12], 0)).toBe(5);
    expect(nextKeyMoment([5, 6, 12], 5)).toBe(6);
    expect(nextKeyMoment([5, 6, 12], 6)).toBe(12);
  });

  it('wraps to the first key moment when none remain', () => {
    expect(nextKeyMoment([5, 6], 6)).toBe(5);
    expect(nextKeyMoment([12, 5, 6], 40)).toBe(5);
  });

  it('returns null only when there are no key moments', () => {
    expect(nextKeyMoment([], 3)).toBeNull();
  });

  it('tolerates unsorted input', () => {
    expect(nextKeyMoment([12, 5, 6], 5)).toBe(6);
  });
});

describe('PlaybackControls', () => {
  const setup = (currentPly: number, maxPly = 40, keyMoments: number[] = [5, 12]) => {
    const onJump = vi.fn();
    const onStep = vi.fn();
    const utils = renderIntl(
      <PlaybackControls
        currentPly={currentPly}
        maxPly={maxPly}
        keyMoments={keyMoments}
        onJump={onJump}
        onStep={onStep}
      />,
    );
    return { ...utils, onJump, onStep };
  };

  it('first jumps to 0 and last jumps to maxPly', () => {
    const { getByTestId, onJump } = setup(10);
    fireEvent.click(getByTestId('pb-first'));
    fireEvent.click(getByTestId('pb-last'));
    expect(onJump).toHaveBeenNthCalledWith(1, 0);
    expect(onJump).toHaveBeenNthCalledWith(2, 40);
  });

  it('prev/next step by ±1 (clamping is the store’s job)', () => {
    const { getByTestId, onStep } = setup(10);
    fireEvent.click(getByTestId('pb-prev'));
    fireEvent.click(getByTestId('pb-next'));
    expect(onStep).toHaveBeenNthCalledWith(1, -1);
    expect(onStep).toHaveBeenNthCalledWith(2, 1);
  });

  it('disables prev/first at the start and next/last at the end', () => {
    const start = setup(0);
    expect((start.getByTestId('pb-first') as HTMLButtonElement).disabled).toBe(true);
    expect((start.getByTestId('pb-prev') as HTMLButtonElement).disabled).toBe(true);
    cleanup();
    const end = setup(40);
    expect((end.getByTestId('pb-next') as HTMLButtonElement).disabled).toBe(true);
    expect((end.getByTestId('pb-last') as HTMLButtonElement).disabled).toBe(true);
  });

  it('Next jumps to the next key moment', () => {
    const { getByTestId, onJump } = setup(6, 40, [5, 12]);
    fireEvent.click(getByTestId('pb-keymoment'));
    expect(onJump).toHaveBeenCalledWith(12);
  });

  it('Next stays enabled at the final ply and wraps to the first key moment', () => {
    const { getByTestId, onJump } = setup(40, 40, [5, 12]);
    const next = getByTestId('pb-keymoment') as HTMLButtonElement;
    expect(next.disabled).toBe(false);
    fireEvent.click(next);
    expect(onJump).toHaveBeenCalledWith(5);
  });

  it('disables Next only when the game has no key moments', () => {
    const { getByTestId } = setup(12, 40, []);
    expect((getByTestId('pb-keymoment') as HTMLButtonElement).disabled).toBe(true);
  });

  it('play toggles to pause and glows accent while playing', () => {
    const { getByTestId } = setup(10);
    const play = getByTestId('pb-play') as HTMLButtonElement;
    expect(play.getAttribute('aria-label')).toBe(gameReview.playback.play);
    expect(play.style.color).toBe('var(--review-text)');
    fireEvent.click(play);
    expect(play.getAttribute('aria-label')).toBe(gameReview.playback.pause);
    expect(play.style.color).toBe('var(--review-accent)');
  });

  it('renders SVG glyphs (ChessBase icons) rather than unicode text', () => {
    const { getByTestId } = setup(10);
    // Each nav control now paints an <svg> icon, not a text glyph.
    for (const id of ['pb-first', 'pb-prev', 'pb-play', 'pb-next', 'pb-last']) {
      expect(getByTestId(id).querySelector('svg')).not.toBeNull();
    }
  });
});
