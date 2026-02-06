
export interface UserGame {
  id: string;
  speed: string;
  lastMoveAt: number;
  status: string;
  winner?: "white" | "black";
  players: {
    white: GameUser;
    black: GameUser;
  };
  pgn: string;
}

export interface GameUser {
  user?: { id: string; name: string };
  rating?: number;
}

export const getSpeedColor = (speed: string): string => {
  switch (speed) {
    case "bullet":
    case "ultrabullet":
      return "#e67e22"; // Orange
    case "blitz":
      return "#f39c12"; // Yellow-orange
    case "rapid":
      return "#27ae60"; // Green
    case "classical":
    case "correspondence":
      return "#2980b9"; // Blue
    default:
      return "#95a5a6"; // Gray
  }
};

export const getSpeedLabel = (speed: string): string => {
  switch (speed) {
    case "ultrabullet":
      return "UltraBullet";
    case "bullet":
      return "Bullet";
    case "blitz":
      return "Blitz";
    case "rapid":
      return "Rapid";
    case "classical":
      return "Classical";
    case "correspondence":
      return "Correspondence";
    default:
      return speed.charAt(0).toUpperCase() + speed.slice(1);
  }
};

export const formatGameDate = (timestamp: number): string => {
  const date = new Date(timestamp);
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

export const fetchUserRecentGames = async (
    username: string
): Promise<UserGame[]> => {
    try {
        const response = await fetch(
            `https://lichess.org/api/games/user/${username}?until=${Date.now()}&max=20&pgnInJson=true&sort=dateDesc`,
            { method: "GET", headers: { accept: "application/x-ndjson" } }
        );

        if (!response.ok) {
            if (response.status === 404) return [];
            throw new Error(`Failed to fetch games: ${response.statusText}`);
        }

        const rawData = await response.text();
        return rawData
            .split("\n")
            .filter(Boolean)
            .map((game) => JSON.parse(game)) as UserGame[];
    } catch (error) {
        console.error("Error fetching recent games:", error);
        return [];
    }
};
