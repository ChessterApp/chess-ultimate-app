import { describe, it, expect } from 'vitest';
import { coachMode, currentMode, initialCoachMode, type CoachModeEvent, type CoachModeState } from '../coach-mode';

const run = (events: CoachModeEvent[], from: CoachModeState = initialCoachMode) => events.reduce(coachMode, from);

describe('coachMode reducer', () => {
  it('starts in explore', () => {
    expect(currentMode(initialCoachMode)).toBe('explore');
  });

  it('a game takes the board to play and back to explore when closed', () => {
    const playing = run([{ type: 'game_started' }]);
    expect(currentMode(playing)).toBe('play');
    expect(currentMode(coachMode(playing, { type: 'game_closed' }))).toBe('explore');
  });

  it('a game started while a tab is viewed brings the study board forward', () => {
    expect(run([{ type: 'view_tab', id: 't1' }, { type: 'game_started' }])).toEqual({ base: 'play', viewerId: null });
  });

  it('puzzle on and off', () => {
    const s = run([{ type: 'puzzle_started' }]);
    expect(currentMode(s)).toBe('puzzle');
    expect(currentMode(coachMode(s, { type: 'puzzle_ended' }))).toBe('explore');
  });

  it('a puzzle cannot replace a live game, and ending a puzzle never ends a game', () => {
    const playing = run([{ type: 'game_started' }]);
    expect(coachMode(playing, { type: 'puzzle_started' })).toBe(playing);
    expect(coachMode(playing, { type: 'puzzle_ended' })).toBe(playing);
  });

  it('«Моменты» take the study board and give it back; never over a live game', () => {
    const s = run([{ type: 'view_tab', id: 't1' }, { type: 'moments_started' }]);
    expect(s).toEqual({ base: 'moments', viewerId: null });
    expect(currentMode(coachMode(s, { type: 'moments_ended' }))).toBe('explore');
    const playing = run([{ type: 'game_started' }]);
    expect(coachMode(playing, { type: 'moments_started' })).toBe(playing);
    expect(coachMode(playing, { type: 'moments_ended' })).toBe(playing);
    // A puzzle the coach sets replaces the review.
    expect(currentMode(coachMode(s, { type: 'puzzle_started' }))).toBe('puzzle');
  });

  it('closing a game while solving a puzzle keeps the puzzle', () => {
    const s = run([{ type: 'puzzle_started' }, { type: 'game_closed' }]);
    expect(currentMode(s)).toBe('puzzle');
  });

  it('a viewer tab shows over the base mode and returns to it', () => {
    const s = run([{ type: 'game_started' }, { type: 'view_tab', id: 'g1' }]);
    expect(currentMode(s)).toBe('viewer');
    expect(s.viewerId).toBe('g1');
    expect(currentMode(coachMode(s, { type: 'view_study' }))).toBe('play');
  });

  it('closing the viewed tab returns to the base; closing another keeps it', () => {
    const s = run([{ type: 'view_tab', id: 'g1' }]);
    expect(coachMode(s, { type: 'tab_closed', id: 'g2' })).toBe(s);
    expect(currentMode(coachMode(s, { type: 'tab_closed', id: 'g1' }))).toBe('explore');
  });

  it('no-op events keep the same state object', () => {
    expect(coachMode(initialCoachMode, { type: 'view_study' })).toBe(initialCoachMode);
    expect(coachMode(initialCoachMode, { type: 'game_closed' })).toBe(initialCoachMode);
    const s = run([{ type: 'view_tab', id: 'g1' }]);
    expect(coachMode(s, { type: 'view_tab', id: 'g1' })).toBe(s);
  });

  it('reset returns to explore', () => {
    expect(run([{ type: 'game_started' }, { type: 'view_tab', id: 'x' }, { type: 'reset' }])).toEqual(initialCoachMode);
  });
});
