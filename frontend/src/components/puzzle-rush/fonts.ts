import { Fraunces } from 'next/font/google';

// Display face for Chesster Native v2 titles ("Fraunces 800"). Kept local to
// Puzzle Rush so shared font modules (and their test mocks) are untouched.
export const fraunces = Fraunces({
  subsets: ['latin'],
  display: 'swap',
  weight: ['800'],
  variable: '--font-fraunces',
});
