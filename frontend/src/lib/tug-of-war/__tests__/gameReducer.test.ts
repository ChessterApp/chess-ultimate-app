import { describe, it, expect } from 'vitest';
import {
  gameReducer,
  initialState,
  currentPuzzle,
  ROPE_LIMIT,
  MAX_WRONG_ATTEMPTS,
  type GameState,
} from '../gameReducer';
import { splitQueues } from '../queues';
import type { TugPuzzle } from '../types';

const puzzle = (id: string): TugPuzzle => ({
  id,
  fen: '8/8/8/8/8/8/8/8 w - - 0 1',
  moves: ['e2e4'],
  rating: 800,
  themes: ['test'],
});

const queue = (prefix: string, n: number) =>
  Array.from({ length: n }, (_, i) => puzzle(`${prefix}${i}`));

function started(qa = queue('a', 6), qb = queue('b', 6)): GameState {
  return gameReducer(initialState(), {
    type: 'START_MATCH',
    teamAName: 'Knights',
    teamBName: 'Rooks',
    queueA: qa,
    queueB: qb,
  });
}

const solveN = (state: GameState, team: 'A' | 'B', n: number): GameState =>
  Array.from({ length: n }).reduce<GameState>(
    (s) => gameReducer(s, { type: 'SOLVE', team }),
    state,
  );

describe('initialState', () => {
  it('starts in setup with default names and a slack rope', () => {
    const s = initialState();
    expect(s.phase).toBe('setup');
    expect(s.teamAName).toBe('Knights');
    expect(s.teamBName).toBe('Rooks');
    expect(s.rope).toBe(0);
    expect(s.winner).toBeNull();
  });
});

describe('START_MATCH', () => {
  it('enters match, seeds both queues and resets state', () => {
    const s = started();
    expect(s.phase).toBe('match');
    expect(s.boardA.puzzles).toHaveLength(6);
    expect(s.boardB.puzzles).toHaveLength(6);
    expect(s.boardA.solved).toBe(0);
    expect(currentPuzzle(s.boardA)?.id).toBe('a0');
  });

  it('falls back to default names when blank', () => {
    const s = gameReducer(initialState(), {
      type: 'START_MATCH',
      teamAName: '   ',
      teamBName: '',
      queueA: queue('a', 2),
      queueB: queue('b', 2),
    });
    expect(s.teamAName).toBe('Knights');
    expect(s.teamBName).toBe('Rooks');
  });
});

describe('SOLVE', () => {
  it('scores the team, advances its board and pulls the rope', () => {
    const s = gameReducer(started(), { type: 'SOLVE', team: 'A' });
    expect(s.boardA.solved).toBe(1);
    expect(s.boardA.index).toBe(1);
    expect(currentPuzzle(s.boardA)?.id).toBe('a1');
    expect(s.rope).toBe(1);
    expect(s.boardB.solved).toBe(0);
  });

  it('rope is the differential of the two teams', () => {
    let s = started();
    s = solveN(s, 'A', 3);
    s = solveN(s, 'B', 1);
    expect(s.rope).toBe(2);
  });

  it('resets the wrong-attempt counter for the puzzle', () => {
    let s = started();
    s = gameReducer(s, { type: 'WRONG', team: 'A' });
    expect(s.boardA.wrongAttempts).toBe(1);
    s = gameReducer(s, { type: 'SOLVE', team: 'A' });
    expect(s.boardA.wrongAttempts).toBe(0);
  });
});

describe('win detection and clamp', () => {
  it('Team A wins when the rope reaches +ROPE_LIMIT', () => {
    const s = solveN(started(), 'A', ROPE_LIMIT);
    expect(s.rope).toBe(ROPE_LIMIT);
    expect(s.winner).toBe('A');
    expect(s.phase).toBe('over');
  });

  it('Team B wins when the rope reaches -ROPE_LIMIT', () => {
    const s = solveN(started(), 'B', ROPE_LIMIT);
    expect(s.rope).toBe(-ROPE_LIMIT);
    expect(s.winner).toBe('B');
    expect(s.phase).toBe('over');
  });

  it('ignores actions once the match is over (rope stays clamped)', () => {
    let s = solveN(started(), 'A', ROPE_LIMIT);
    s = gameReducer(s, { type: 'SOLVE', team: 'A' });
    s = gameReducer(s, { type: 'WRONG', team: 'B' });
    expect(s.rope).toBe(ROPE_LIMIT);
    expect(s.boardA.solved).toBe(ROPE_LIMIT);
  });
});

describe('WRONG and 3-wrong auto-skip', () => {
  it('counts wrong moves without touching the rope or score', () => {
    let s = started();
    s = gameReducer(s, { type: 'WRONG', team: 'A' });
    s = gameReducer(s, { type: 'WRONG', team: 'A' });
    expect(s.boardA.wrongAttempts).toBe(2);
    expect(s.rope).toBe(0);
    expect(s.boardA.solved).toBe(0);
    expect(currentPuzzle(s.boardA)?.id).toBe('a0');
  });

  it('discards the puzzle after MAX_WRONG_ATTEMPTS and advances', () => {
    let s = started();
    for (let i = 0; i < MAX_WRONG_ATTEMPTS; i++) {
      s = gameReducer(s, { type: 'WRONG', team: 'A' });
    }
    expect(s.boardA.wrongAttempts).toBe(0);
    expect(s.boardA.skips).toBe(1);
    expect(s.boardA.solved).toBe(0);
    expect(currentPuzzle(s.boardA)?.id).toBe('a1');
    expect(s.rope).toBe(0);
  });
});

describe('currentPuzzle wrap-around', () => {
  it('cycles through the queue so a board never runs dry', () => {
    const s = started(queue('a', 2), queue('b', 2));
    const after = solveN(s, 'A', 2);
    // index 2 % length 2 === 0 → back to the first puzzle
    expect(currentPuzzle(after.boardA)?.id).toBe('a0');
  });
});

describe('REMATCH', () => {
  it('returns to setup keeping the team names', () => {
    let s = solveN(started(), 'A', 2);
    s = gameReducer(s, { type: 'REMATCH' });
    expect(s.phase).toBe('setup');
    expect(s.teamAName).toBe('Knights');
    expect(s.teamBName).toBe('Rooks');
    expect(s.boardA.solved).toBe(0);
  });
});

describe('splitQueues', () => {
  it('produces two disjoint queues covering the whole pool', () => {
    const pool = queue('p', 40);
    const { queueA, queueB } = splitQueues(pool, () => 0.42);
    expect(queueA.length + queueB.length).toBe(40);
    const ids = new Set([...queueA, ...queueB].map((p) => p.id));
    expect(ids.size).toBe(40);
    const aIds = new Set(queueA.map((p) => p.id));
    expect(queueB.some((p) => aIds.has(p.id))).toBe(false);
  });
});
