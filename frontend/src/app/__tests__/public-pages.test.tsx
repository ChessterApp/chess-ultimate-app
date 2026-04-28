import { describe, it, expect } from 'vitest';

describe('Public Tournaments Page', () => {
  it('exports a default function component', async () => {
    const module = await import('../tournaments/page');
    expect(typeof module.default).toBe('function');
  });

  it('is a client component', async () => {
    const fs = await import('fs');
    const path = await import('path');
    const content = fs.readFileSync(
      path.resolve(__dirname, '../tournaments/page.tsx'),
      'utf-8'
    );
    expect(content).toContain("'use client'");
  });
});

describe('Tournament Detail Page', () => {
  it('exports a default async function (server component)', async () => {
    const module = await import('../tournaments/[id]/page');
    expect(typeof module.default).toBe('function');
  });
});

describe('Tournament Results Page', () => {
  it('exports a default async function (server component)', async () => {
    const module = await import('../tournaments/[id]/results/page');
    expect(typeof module.default).toBe('function');
  });
});

describe('Tournament Register Page', () => {
  it('exports a default function component', async () => {
    const module = await import('../tournaments/[id]/register/page');
    expect(typeof module.default).toBe('function');
  });
});

describe('Leaderboard Page', () => {
  it('exports a default function component', async () => {
    const module = await import('../leaderboard/page');
    expect(typeof module.default).toBe('function');
  });

  it('is a client component', async () => {
    const fs = await import('fs');
    const path = await import('path');
    const content = fs.readFileSync(
      path.resolve(__dirname, '../leaderboard/page.tsx'),
      'utf-8'
    );
    expect(content).toContain("'use client'");
  });
});
