import { describe, it, expect } from 'vitest';

describe('Admin Billing Page', () => {
  it('exports a default function component', async () => {
    const module = await import('../admin/billing/page');
    expect(typeof module.default).toBe('function');
  });

  it('is a client component', async () => {
    const fs = await import('fs');
    const path = await import('path');
    const content = fs.readFileSync(
      path.resolve(__dirname, '../admin/billing/page.tsx'),
      'utf-8'
    );
    expect(content).toContain("'use client'");
  });
});

describe('Admin Analytics Page', () => {
  it('exports a default function component', async () => {
    const module = await import('../admin/analytics/page');
    expect(typeof module.default).toBe('function');
  });

  it('is a client component', async () => {
    const fs = await import('fs');
    const path = await import('path');
    const content = fs.readFileSync(
      path.resolve(__dirname, '../admin/analytics/page.tsx'),
      'utf-8'
    );
    expect(content).toContain("'use client'");
  });
});

describe('Admin Tournaments Page', () => {
  it('exports a default function component', async () => {
    const module = await import('../admin/tournaments/page');
    expect(typeof module.default).toBe('function');
  });

  it('is a client component', async () => {
    const fs = await import('fs');
    const path = await import('path');
    const content = fs.readFileSync(
      path.resolve(__dirname, '../admin/tournaments/page.tsx'),
      'utf-8'
    );
    expect(content).toContain("'use client'");
  });
});

describe('Admin New Tournament Page', () => {
  it('exports a default function component', async () => {
    const module = await import('../admin/tournaments/new/page');
    expect(typeof module.default).toBe('function');
  });
});

describe('Admin Edit Tournament Page', () => {
  it('exports a default function component', async () => {
    const module = await import('../admin/tournaments/[id]/edit/page');
    expect(typeof module.default).toBe('function');
  });
});

describe('Admin Tournament Pairings Page', () => {
  it('exports a default function component', async () => {
    const module = await import('../admin/tournaments/[id]/pairings/page');
    expect(typeof module.default).toBe('function');
  });
});

describe('Admin Tournament Results Page', () => {
  it('exports a default function component', async () => {
    const module = await import('../admin/tournaments/[id]/results/page');
    expect(typeof module.default).toBe('function');
  });
});
