import type { CreateRunResponse, MoveResponse, RushPuzzle } from '../types';

/** Lichess 00008: setup f2g3, then e6e7 b2b1 b3c1 b1c1 h6c1 (user plays White). */
export const MULTI: RushPuzzle = {
  id: '00008',
  index: 0,
  fen: 'r6k/pp2r2p/4Rp1Q/3p4/8/1N1P2R1/PqP2bPP/7K b - - 0 24',
  setup_move: 'f2g3',
  rating: 1800,
  color: 'white',
};

export const NEXT: RushPuzzle = {
  id: '000aY',
  index: 1,
  fen: 'r4rk1/pp3ppp/2n1b3/q1pp2B1/8/P1Q2NP1/1PP1PP1P/2KR3R w - - 0 15',
  setup_move: 'g5e7',
  rating: 1450,
  color: 'black',
};

export const T0 = Date.parse('2026-10-12T10:00:00Z');

export function created(overrides: Partial<CreateRunResponse> = {}): CreateRunResponse {
  return {
    run_id: '11111111-2222-3333-4444-555555555555',
    mode: '3min',
    started_at: '2026-10-12T10:00:03Z',
    deadline: '2026-10-12T10:03:03Z',
    server_now: '2026-10-12T10:00:00Z',
    puzzle: MULTI,
    ...overrides,
  };
}

export function moveRes(overrides: Partial<MoveResponse>): MoveResponse {
  return {
    run_id: '11111111-2222-3333-4444-555555555555',
    mode: '3min',
    result: 'correct',
    score: 0,
    strikes: 0,
    streak: 0,
    started_at: '2026-10-12T10:00:03Z',
    deadline: '2026-10-12T10:03:03Z',
    server_now: '2026-10-12T10:00:10Z',
    run_over: false,
    ...overrides,
  };
}

export const RESULTS = {
  score: 4,
  is_new_pb: false,
  longest_streak: 3,
  highest_solved_rating: 1310,
  avg_ms_per_puzzle: 4200,
  duration_ms: 60000,
  personal_rank: 2,
  global_rank: { daily: 5, weekly: 9, all: 40 },
};
