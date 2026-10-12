import { Fraunces, Fredoka, Nunito } from 'next/font/google'

// Display + body fonts for the playful "Hero Trading Cards" bot tiles.
// Both are variable fonts, so weight is controlled via CSS font-weight.
export const fredoka = Fredoka({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-fredoka',
})

export const nunito = Nunito({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-nunito',
})

// Display face for Chesster Native v2 titles (Puzzle Rush "Fraunces 800").
export const fraunces = Fraunces({
  subsets: ['latin'],
  display: 'swap',
  weight: ['800'],
  variable: '--font-fraunces',
})
