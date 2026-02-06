export interface ChessDotComPlayer {
    rating: number;
    result: string;
    "@id": string;
    username: string;
    uuid: string;
}

export interface ChessDotComGame {
    url: string;
    pgn: string;
    time_control: string;
    end_time: number;
    rated: boolean;
    tcn: string;
    uuid: string;
    initial_setup: string;
    fen: string;
    time_class: string;
    rules: string;
    white: ChessDotComPlayer;
    black: ChessDotComPlayer;
    eco?: string;
    accuracies?: {
        white: number;
        black: number;
    };
}

export interface ChessDotComArchive {
    games: ChessDotComGame[];
}

/**
 * Fetches the list of available game archives for a Chess.com user
 * @param username Chess.com username
 * @returns Array of archive URLs (e.g., "https://api.chess.com/pub/player/hikaru/games/2025/01")
 */
export const fetchUserArchives = async (
    username: string
): Promise<string[]> => {
    try {
        const response = await fetch(
            `https://api.chess.com/pub/player/${username.toLowerCase()}/games/archives`,
            { method: "GET", headers: { accept: "application/json" } }
        );

        if (!response.ok) {
            if (response.status === 404) return [];
            throw new Error(`Failed to fetch archives: ${response.statusText}`);
        }

        const data: { archives: string[] } = await response.json();
        return data.archives;
    } catch (error) {
        console.error("Error fetching user archives:", error);
        return [];
    }
};

/**
 * Fetches recent games for a Chess.com user from their most recent archive
 * @param username Chess.com username
 * @param limit Maximum number of games to return (default: 20)
 * @returns Array of ChessDotComGame objects, newest first
 */
export const fetchUserRecentGames = async (
    username: string,
    limit: number = 20
): Promise<ChessDotComGame[]> => {
    try {
        // First, get the list of archives
        const archives = await fetchUserArchives(username);
        if (archives.length === 0) return [];

        // Get the most recent archive (last in the array)
        const mostRecentArchive = archives[archives.length - 1];

        const response = await fetch(mostRecentArchive, {
            method: "GET",
            headers: { accept: "application/json" }
        });

        if (!response.ok) {
            throw new Error(`Failed to fetch games: ${response.statusText}`);
        }

        const data: ChessDotComArchive = await response.json();

        // Return the most recent games (already sorted by end_time in API response)
        // Reverse to get newest first, then limit
        return data.games.reverse().slice(0, limit);
    } catch (error) {
        console.error("Error fetching recent games:", error);
        return [];
    }
};

/**
 * Formats a Unix timestamp to a readable date string
 * @param timestamp Unix timestamp in seconds
 * @returns Formatted date string (e.g., "Jan 4, 2025 at 00:08")
 */
export const formatGameDate = (timestamp: number): string => {
    const date = new Date(timestamp * 1000);
    return date.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
};

/**
 * Gets the time class icon/label for display
 * @param timeClass Chess.com time class (bullet, blitz, rapid, daily)
 * @returns Display label
 */
export const getTimeClassLabel = (timeClass: string): string => {
    const labels: { [key: string]: string } = {
        bullet: "Bullet",
        blitz: "Blitz",
        rapid: "Rapid",
        daily: "Daily",
        classical: "Classical",
    };
    return labels[timeClass] || timeClass;
};

/**
 * Gets a color code for the time class
 * @param timeClass Chess.com time class
 * @returns Hex color code
 */
export const getTimeClassColor = (timeClass: string): string => {
    const colors: { [key: string]: string } = {
        bullet: "#e74c3c",  // Red
        blitz: "#f39c12",   // Orange
        rapid: "#27ae60",   // Green
        daily: "#3498db",   // Blue
        classical: "#9b59b6", // Purple
    };
    return colors[timeClass] || "#95a5a6"; // Gray default
};
