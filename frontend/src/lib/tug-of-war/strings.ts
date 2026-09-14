/**
 * User-facing strings for Tug of War, kept in one place (English only for M1,
 * i18n-ready per the PRD). Note: never reference the placeholder art's origin
 * in any user-facing string.
 */
export const TUG_STRINGS = {
  title: 'Chess Tug of War',
  subtitle: 'Two teams. Two boards. Pull the rope to your side.',
  teamALabel: 'Team A name',
  teamBLabel: 'Team B name',
  levelLabel: 'Difficulty',
  themesLabel: 'Themes (optional)',
  start: 'Start match',
  loading: 'Loading puzzles…',
  offlineNotice: 'Offline puzzle set',
  howToTitle: 'How to play',
  how: [
    'Each team solves its own chess puzzles on its board.',
    'Play the move on the board — tap a piece, then tap its square.',
    'Every solved puzzle pulls the rope one step toward your side.',
    'Drag the rope fully to your side to win. Wrong moves cost nothing.',
  ],
  defaultTeamA: 'Knights',
  defaultTeamB: 'Rooks',
  yourMove: 'Your move',
  skipped: 'Skipped — next puzzle!',
  wins: (team: string) => `TEAM ${team} WINS!`,
  rematch: 'Rematch',
  muteOn: 'Mute sound',
  muteOff: 'Unmute sound',
} as const;
