import { Fredoka, Nunito } from 'next/font/google'

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
