/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));
vi.mock('next-intl', () => ({ useTranslations: () => (k: string) => k }));
const trackMock = vi.hoisted(() => vi.fn());
vi.mock('@/lib/analytics/events', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/analytics/events')>()),
  track: trackMock,
}));

import { HeroButtons } from '../HeroButtons';
import { CTAButton } from '../CTAButton';

afterEach(() => {
  cleanup();
  push.mockReset();
  trackMock.mockReset();
});

describe('landing_cta_clicked', () => {
  it('hero sign-up / sign-in buttons track location=hero then navigate', () => {
    render(<HeroButtons />);
    fireEvent.click(screen.getByText('common.getStarted'));
    expect(trackMock).toHaveBeenCalledWith('landing_cta_clicked', { location: 'hero', target: 'sign_up' });
    expect(push).toHaveBeenCalledWith('/sign-up');
    fireEvent.click(screen.getByText('landing.alreadyHaveAccount'));
    expect(trackMock).toHaveBeenCalledWith('landing_cta_clicked', { location: 'hero', target: 'sign_in' });
  });

  it('CTAButton tracks its location + target', () => {
    render(<CTAButton href="/sign-up" location="footer">go</CTAButton>);
    fireEvent.click(screen.getByText('go'));
    expect(trackMock).toHaveBeenCalledWith('landing_cta_clicked', { location: 'footer', target: '/sign-up' });
    expect(push).toHaveBeenCalledWith('/sign-up');
  });
});
