import { describe, it, expect } from 'vitest';

describe('RatingBadge', () => {
  it('exports a default function component', async () => {
    const module = await import('../ratings/RatingBadge');
    expect(typeof module.default).toBe('function');
  });

  it('is a client component', async () => {
    const fs = await import('fs');
    const path = await import('path');
    const content = fs.readFileSync(
      path.resolve(__dirname, '../ratings/RatingBadge.tsx'),
      'utf-8'
    );
    expect(content).toContain("'use client'");
  });
});

describe('LeagueBadge', () => {
  it('exports a default function component', async () => {
    const module = await import('../ratings/LeagueBadge');
    expect(typeof module.default).toBe('function');
  });

  it('is a client component', async () => {
    const fs = await import('fs');
    const path = await import('path');
    const content = fs.readFileSync(
      path.resolve(__dirname, '../ratings/LeagueBadge.tsx'),
      'utf-8'
    );
    expect(content).toContain("'use client'");
  });
});

describe('RatingChart', () => {
  it('exports a default function component', async () => {
    const module = await import('../ratings/RatingChart');
    expect(typeof module.default).toBe('function');
  });

  it('is a client component', async () => {
    const fs = await import('fs');
    const path = await import('path');
    const content = fs.readFileSync(
      path.resolve(__dirname, '../ratings/RatingChart.tsx'),
      'utf-8'
    );
    expect(content).toContain("'use client'");
  });
});

describe('Leaderboard', () => {
  it('exports a default function component', async () => {
    const module = await import('../ratings/Leaderboard');
    expect(typeof module.default).toBe('function');
  });

  it('is a client component', async () => {
    const fs = await import('fs');
    const path = await import('path');
    const content = fs.readFileSync(
      path.resolve(__dirname, '../ratings/Leaderboard.tsx'),
      'utf-8'
    );
    expect(content).toContain("'use client'");
  });
});
