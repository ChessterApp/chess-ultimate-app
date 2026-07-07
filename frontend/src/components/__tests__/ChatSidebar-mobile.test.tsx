// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import React from 'react';

// Echo translation keys so we can assert on rendered labels.
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

import ChatSidebar from '../ChatSidebar';
import type { ChatSession } from '@/hooks/useChatSessions';

const sessions: ChatSession[] = [
  {
    id: 's1',
    title: 'First session',
    messages: [],
    createdAt: 1,
    updatedAt: 2,
    isActive: true,
    currentFen: 'startpos',
  },
];

function renderSidebar(overrides: Partial<React.ComponentProps<typeof ChatSidebar>> = {}) {
  const props = {
    sessions,
    currentSessionId: 's1',
    onNewChat: vi.fn(),
    onSelectSession: vi.fn(),
    onDeleteSession: vi.fn(),
    onRenameSession: vi.fn(),
    onToggleCollapse: vi.fn(),
    isCollapsed: false,
    ...overrides,
  };
  return { props, ...render(<ChatSidebar {...props} />) };
}

describe('ChatSidebar mobile drawer', () => {
  beforeEach(() => {
    document.body.style.overflow = '';
  });

  it('renders a mobile trigger button (44px+ touch target)', () => {
    renderSidebar();
    const trigger = screen.getByRole('button', { name: /open chat sessions/i });
    expect(trigger).toBeTruthy();
    expect(trigger.className).toContain('md:hidden');
    // 44px+ touch target (h-12 w-12 = 48px)
    expect(trigger.className).toMatch(/h-12/);
    expect(trigger.className).toMatch(/w-12/);
  });

  const getDrawer = (container: HTMLElement) =>
    container.querySelector('aside[aria-label="Chat sessions"]') as HTMLElement;

  it('drawer is closed by default and opens on trigger click', () => {
    const { container } = renderSidebar();
    const drawer = getDrawer(container);
    // Closed: off-canvas + aria-hidden
    expect(drawer.className).toContain('-translate-x-full');
    expect(drawer.getAttribute('aria-hidden')).toBe('true');

    fireEvent.click(screen.getByRole('button', { name: /open chat sessions/i }));

    expect(drawer.className).toContain('translate-x-0');
    expect(drawer.getAttribute('aria-hidden')).toBe('false');
  });

  it('drawer contains the session list and a close button', () => {
    const { container } = renderSidebar();
    fireEvent.click(screen.getByRole('button', { name: /open chat sessions/i }));
    const drawer = getDrawer(container);
    // Session title is reachable inside the drawer
    expect(within(drawer).getByText('First session')).toBeTruthy();
    expect(screen.getByRole('button', { name: /close chat sessions/i })).toBeTruthy();
  });

  it('mobile drawer is still available when the desktop sidebar is collapsed', () => {
    const { container } = renderSidebar({ isCollapsed: true });
    expect(screen.getByRole('button', { name: /open chat sessions/i })).toBeTruthy();
    expect(getDrawer(container)).toBeTruthy();
  });

  it('selecting a session in the drawer closes it', () => {
    const { props, container } = renderSidebar();
    fireEvent.click(screen.getByRole('button', { name: /open chat sessions/i }));
    const drawer = getDrawer(container);
    fireEvent.click(within(drawer).getByText('First session'));
    expect(props.onSelectSession).toHaveBeenCalledWith('s1');
    expect(drawer.className).toContain('-translate-x-full');
  });
});
