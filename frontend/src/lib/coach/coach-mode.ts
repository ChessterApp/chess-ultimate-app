/**
 * The coach page's mode: what the board is doing and which strip sits around
 * it. One reducer instead of the booleans that used to decide it (game set,
 * puzzle on, a game tab active).
 *
 * `base` is what the study board is used for; a viewer tab is shown over it
 * and closing the tab returns to the base mode (a live game survives a look at
 * a master game).
 */

export type CoachMode = 'explore' | 'play' | 'puzzle' | 'moments' | 'viewer';
type BaseMode = Exclude<CoachMode, 'viewer'>;

export interface CoachModeState {
  base: BaseMode;
  /** The board id of the game tab being viewed, if any. */
  viewerId: string | null;
}

export type CoachModeEvent =
  | { type: 'game_started' }
  | { type: 'game_closed' }
  | { type: 'puzzle_started' }
  | { type: 'puzzle_ended' }
  /** «Моменты»: a game review replayed step by step on the study board. */
  | { type: 'moments_started' }
  | { type: 'moments_ended' }
  | { type: 'view_tab'; id: string }
  | { type: 'view_study' }
  | { type: 'tab_closed'; id: string }
  | { type: 'reset' };

export const initialCoachMode: CoachModeState = { base: 'explore', viewerId: null };

export function coachMode(state: CoachModeState, event: CoachModeEvent): CoachModeState {
  switch (event.type) {
    case 'game_started':
      // The game is played on the study board: it comes to the front.
      return { base: 'play', viewerId: null };
    case 'game_closed':
      return state.base === 'play' ? { ...state, base: 'explore' } : state;
    case 'puzzle_started':
      // A live game owns the study board; the coach can't swap a puzzle in.
      return state.base === 'play' ? state : { ...state, base: 'puzzle' };
    case 'puzzle_ended':
      return state.base === 'puzzle' ? { ...state, base: 'explore' } : state;
    case 'moments_started':
      // Like a puzzle: not over a live game; the study board comes to the front.
      return state.base === 'play' ? state : { base: 'moments', viewerId: null };
    case 'moments_ended':
      return state.base === 'moments' ? { ...state, base: 'explore' } : state;
    case 'view_tab':
      return state.viewerId === event.id ? state : { ...state, viewerId: event.id };
    case 'view_study':
      return state.viewerId === null ? state : { ...state, viewerId: null };
    case 'tab_closed':
      return state.viewerId === event.id ? { ...state, viewerId: null } : state;
    case 'reset':
      return initialCoachMode;
  }
}

/** The mode the UI renders. */
export function currentMode(state: CoachModeState): CoachMode {
  return state.viewerId ? 'viewer' : state.base;
}
