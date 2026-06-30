import { describe, it, expect } from 'vitest';

import { buildClerkLocalization } from '@/lib/clerk-localization';

describe('buildClerkLocalization', () => {
  it('interpolates appName into the EN sign-in/sign-up titles', () => {
    const loc = buildClerkLocalization('en', 'Chess Empire') as {
      signIn: { start: { title: string } };
      signUp: { start: { title: string } };
    };
    expect(loc.signIn.start.title).toBe('Sign in to Chess Empire');
    expect(loc.signUp.start.title).toBe('Create your Chess Empire account');
  });

  it('falls back to "Chesster" for the apex', () => {
    const loc = buildClerkLocalization('en', 'Chesster') as {
      signIn: { start: { title: string } };
    };
    expect(loc.signIn.start.title).toBe('Sign in to Chesster');
  });

  it('interpolates across ru/kz too', () => {
    const ru = buildClerkLocalization('ru', 'Chess Empire') as {
      signIn: { start: { title: string } };
    };
    expect(ru.signIn.start.title).toBe('Войти в Chess Empire');

    const kz = buildClerkLocalization('kz', 'Chess Empire') as {
      signUp: { start: { title: string } };
    };
    expect(kz.signUp.start.title).toBe('Chess Empire аккаунтын жасау');
  });

  it('defaults to EN when the locale is unknown', () => {
    const loc = buildClerkLocalization('zz', 'Chess Empire') as {
      signIn: { start: { title: string } };
    };
    expect(loc.signIn.start.title).toBe('Sign in to Chess Empire');
  });

  it('leaves field placeholders untouched (no ${appName} present)', () => {
    const loc = buildClerkLocalization('en', 'Chess Empire') as {
      formFieldInputPlaceholder__emailAddress: string;
    };
    expect(loc.formFieldInputPlaceholder__emailAddress).toBe('Email');
  });
});
