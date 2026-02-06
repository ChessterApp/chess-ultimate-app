export type Platform = "lichess" | "chessdotcom";

export interface GameFilters {
  // Platform selection
  platform: Platform;

  // User and date filters
  username: string;
  downloadAll: boolean; // All games vs subset

  // Player color filters
  includeWhite: boolean;
  includeBlack: boolean;

  // Game variant filters
  includeChess: boolean;
  includeChess960: boolean;
  includeBugHouse: boolean;
  includeKingOfTheHill: boolean;
  includeThreeCheck: boolean;
  includeCrazyHouse: boolean;

  // Time control filters
  includeUltraBullet: boolean;
  includeBullet: boolean;
  includeBlitz: boolean;
  includeRapid: boolean;
  includeClassical: boolean;
  includeDaily: boolean;

  // Date range filters
  dateFilterType: "all" | "past18months" | "between";
  startDate?: string;
  endDate?: string;

  // Additional filters
  ratedOnly: boolean;
}

export interface DownloadProgress {
  currentMonth: string;
  totalGames: number;
  processedGames: number;
  percentage: number;
  status: "idle" | "downloading" | "processing" | "complete" | "error";
  errorMessage?: string;
}

export const DEFAULT_FILTERS: GameFilters = {
  platform: "lichess",
  username: "",
  downloadAll: false,
  includeWhite: true,
  includeBlack: true,
  includeChess: true,
  includeChess960: false,
  includeBugHouse: false,
  includeKingOfTheHill: false,
  includeThreeCheck: false,
  includeCrazyHouse: false,
  includeUltraBullet: false,
  includeBullet: false,
  includeBlitz: false,
  includeRapid: true,
  includeClassical: true,
  includeDaily: false,
  dateFilterType: "all",
  ratedOnly: false,
};

/**
 * Filters games based on selected criteria
 */
export function filterGames(games: any[], filters: GameFilters, platform: Platform): any[] {
  return games.filter(game => {
    // Color filter
    const userColor = platform === "lichess"
      ? (game.players.white.user?.name?.toLowerCase() === filters.username.toLowerCase() ? "white" : "black")
      : (game.white.username.toLowerCase() === filters.username.toLowerCase() ? "white" : "black");

    if (userColor === "white" && !filters.includeWhite) return false;
    if (userColor === "black" && !filters.includeBlack) return false;

    // Time control filter
    const timeClass = platform === "lichess" ? game.speed : game.time_class;
    if (timeClass === "ultraBullet" && !filters.includeUltraBullet) return false;
    if (timeClass === "bullet" && !filters.includeBullet) return false;
    if (timeClass === "blitz" && !filters.includeBlitz) return false;
    if (timeClass === "rapid" && !filters.includeRapid) return false;
    if (timeClass === "classical" && !filters.includeClassical) return false;
    if (timeClass === "daily" && !filters.includeDaily) return false;

    // Variant filter (Lichess specific)
    if (platform === "lichess") {
      const variant = game.variant || "standard";
      if (variant === "standard" && !filters.includeChess) return false;
      if (variant === "chess960" && !filters.includeChess960) return false;
      if (variant === "kingOfTheHill" && !filters.includeKingOfTheHill) return false;
      if (variant === "threeCheck" && !filters.includeThreeCheck) return false;
      if (variant === "crazyhouse" && !filters.includeCrazyHouse) return false;
    }

    // Rated filter
    if (filters.ratedOnly && !game.rated) return false;

    return true;
  });
}

/**
 * Generate PGN file content from filtered games
 */
export function generatePGN(games: any[], platform: Platform): string {
  return games.map(game => {
    if (platform === "lichess") {
      return game.pgn;
    } else {
      // Chess.com already has PGN in the game object
      return game.pgn;
    }
  }).join("\n\n");
}

/**
 * Download PGN file to user's computer
 */
export function downloadPGNFile(pgn: string, filename: string) {
  const blob = new Blob([pgn], { type: "application/x-chess-pgn" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
