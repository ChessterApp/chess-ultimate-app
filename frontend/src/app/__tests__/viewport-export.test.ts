import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

// The root layout must export a `viewport` with `viewportFit: 'cover'` so that
// `viewport-fit=cover` is emitted — without it every `env(safe-area-inset-*)`
// / `pb-safe` rule in the app is inert on notch/home-bar iPhones.
describe('root layout viewport export', () => {
  const source = fs.readFileSync(
    path.resolve(__dirname, '../layout.tsx'),
    'utf-8'
  );

  it('exports a viewport constant', () => {
    expect(source).toMatch(/export const viewport\s*:\s*Viewport/);
  });

  it('imports the Viewport type from next', () => {
    expect(source).toMatch(/import type \{[^}]*\bViewport\b[^}]*\} from ["']next["']/);
  });

  it('sets viewportFit to cover', () => {
    expect(source).toMatch(/viewportFit:\s*['"]cover['"]/);
  });

  it('keeps pb-safe defined in globals.css', () => {
    const css = fs.readFileSync(
      path.resolve(__dirname, '../globals.css'),
      'utf-8'
    );
    expect(css).toMatch(/\.pb-safe\s*\{[^}]*safe-area-inset-bottom/);
  });
});
