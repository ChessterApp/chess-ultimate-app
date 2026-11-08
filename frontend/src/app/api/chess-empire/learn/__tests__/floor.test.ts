/**
 * Tests for GET /api/chess-empire/learn/floor — a thin JSON wrapper over
 * resolveCeLevelFloor (decision logic covered in lib/__tests__/learn-ce-floor).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const floorStore: { current: number | undefined } = { current: 3 };
vi.mock('@/lib/learn-ce-floor', () => ({
  resolveCeLevelFloor: vi.fn(async () => floorStore.current),
}));

import { GET } from '../floor/route';

beforeEach(() => {
  floorStore.current = 3;
});

describe('GET /api/chess-empire/learn/floor', () => {
  it('returns the resolved level floor', async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ floor: 3 });
  });

  it('returns floor:null (never 401) when no floor applies', async () => {
    floorStore.current = undefined;
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ floor: null });
  });
});
