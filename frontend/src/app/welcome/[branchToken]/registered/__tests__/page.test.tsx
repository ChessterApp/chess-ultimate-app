/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render } from '@testing-library/react';

vi.mock('next-intl/server', () => ({
  getTranslations: async () => (key: string) => key,
}));

vi.mock('next/image', () => ({
  default: ({ alt, src }: { alt: string; src: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} src={src} />
  ),
}));

vi.mock('next/link', () => ({
  default: ({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode;
    href: string;
    [k: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import RegisteredPage from '../page';

describe('RegisteredPage', () => {
  afterEach(() => cleanup());

  it('renders both buttons with correct hrefs', async () => {
    const ui = await RegisteredPage();
    const { container } = render(ui);

    const signIn = container.querySelector('a[href="/sign-in"]');
    expect(signIn).not.toBeNull();
    expect(signIn?.textContent).toContain('signIn');

    const contact = container.querySelector('a[href^="mailto:"]');
    expect(contact).not.toBeNull();
    expect(contact?.getAttribute('href')).toBe('mailto:hello@chess-empire.kz');
    expect(contact?.textContent).toContain('contact');
  });

  it('renders the duplicate-account copy', async () => {
    const ui = await RegisteredPage();
    const { container } = render(ui);
    expect(container.textContent).toContain('title');
    expect(container.textContent).toContain('body');
  });
});
