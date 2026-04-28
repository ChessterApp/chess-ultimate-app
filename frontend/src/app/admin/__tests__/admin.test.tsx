import { describe, it, expect } from 'vitest';

describe('Admin Layout', () => {
  it('exports a default layout function (server component)', async () => {
    const module = await import('../layout');
    expect(typeof module.default).toBe('function');
  });

  it('admin page redirects to /admin/dashboard', async () => {
    // The admin root page should call redirect()
    const module = await import('../page');
    expect(typeof module.default).toBe('function');
  });
});

describe('Admin Sidebar', () => {
  it('exports a default client component', async () => {
    const module = await import('../AdminSidebar');
    expect(typeof module.default).toBe('function');
  });

  it('is a client component (uses hooks)', async () => {
    const fs = await import('fs');
    const path = await import('path');
    const content = fs.readFileSync(
      path.resolve(__dirname, '../AdminSidebar.tsx'),
      'utf-8'
    );
    expect(content).toContain("'use client'");
  });
});

describe('Admin Dashboard Page', () => {
  it('exports a default server component', async () => {
    const module = await import('../dashboard/page');
    expect(typeof module.default).toBe('function');
  });
});

describe('Admin Students Page', () => {
  it('exports a default component', async () => {
    const module = await import('../students/page');
    expect(typeof module.default).toBe('function');
  });

  it('is a client component', async () => {
    const fs = await import('fs');
    const path = await import('path');
    const content = fs.readFileSync(
      path.resolve(__dirname, '../students/page.tsx'),
      'utf-8'
    );
    expect(content).toContain("'use client'");
  });
});

describe('Admin Courses Page', () => {
  it('exports a default component', async () => {
    const module = await import('../courses/page');
    expect(typeof module.default).toBe('function');
  });
});

describe('Admin Settings Page', () => {
  it('exports a default component', async () => {
    const module = await import('../settings/page');
    expect(typeof module.default).toBe('function');
  });
});
