import { describe, expect, it } from 'vitest';

import { isFromBrowserExtension } from '../errorReporter';

describe('isFromBrowserExtension', () => {
  it('recognises an error thrown inside an extension (stack or script URL)', () => {
    // Seen on /coach 2026-09-27: an anti-tracking extension's rejection became
    // six "An unexpected error occurred" toasts.
    const err = new TypeError("Cannot read properties of undefined (reading 'M_ID')");
    err.stack = `${err.message}\n    at Y (chrome-extension://eppiocemhmnlbhjplcgkofciiegomcon/executors/200.js:1:761)`;
    expect(isFromBrowserExtension(err)).toBe(true);
    expect(isFromBrowserExtension(new Error('x'), 'moz-extension://abc/content.js')).toBe(true);
    expect(isFromBrowserExtension('at f (safari-web-extension://id/script.js:1:1)')).toBe(true);
  });

  it("keeps the site's own errors", () => {
    const err = new Error('boom');
    err.stack = 'Error: boom\n    at CoachChat (http://localhost:3000/_next/static/chunks/app.js:1:1)';
    expect(isFromBrowserExtension(err)).toBe(false);
    expect(isFromBrowserExtension('plain reason')).toBe(false);
    expect(isFromBrowserExtension(undefined)).toBe(false);
  });
});
