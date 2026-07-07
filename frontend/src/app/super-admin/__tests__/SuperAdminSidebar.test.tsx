// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';

vi.mock('next/navigation', () => ({
  usePathname: () => '/super-admin',
}));

import SuperAdminSidebar from '../SuperAdminSidebar';
import SuperAdminShell from '../SuperAdminShell';

describe('SuperAdminSidebar mobile drawer', () => {
  it('renders an off-canvas mobile drawer when closed', () => {
    const { container } = render(<SuperAdminSidebar mobileOpen={false} />);
    const drawer = container.querySelector('aside.md\\:hidden');
    expect(drawer).toBeTruthy();
    expect(drawer!.className).toContain('-translate-x-full');
  });

  it('slides the drawer in when mobileOpen is true', () => {
    const { container } = render(<SuperAdminSidebar mobileOpen={true} />);
    const drawer = container.querySelector('aside.md\\:hidden');
    expect(drawer!.className).toContain('translate-x-0');
  });

  it('keeps the desktop sidebar (hidden below md)', () => {
    const { container } = render(<SuperAdminSidebar mobileOpen={false} />);
    const desktop = container.querySelector('aside.md\\:flex');
    expect(desktop).toBeTruthy();
    expect(desktop!.className).toContain('hidden');
  });
});

describe('SuperAdminShell mobile hamburger', () => {
  it('renders a hamburger that opens the drawer', () => {
    const { container } = render(
      <SuperAdminShell>
        <div>content</div>
      </SuperAdminShell>
    );
    const hamburger = screen.getByRole('button', { name: /open menu/i });
    // 44px+ touch target
    expect(hamburger.className).toMatch(/h-11/);
    expect(hamburger.className).toMatch(/w-11/);

    const drawer = container.querySelector('aside.md\\:hidden')!;
    expect(drawer.className).toContain('-translate-x-full');

    fireEvent.click(hamburger);
    expect(drawer.className).toContain('translate-x-0');
  });
});
