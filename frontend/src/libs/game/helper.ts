

export function parsePgnChapters(pgnText: string) {
  const chapterBlocks = pgnText.split(/\n\n(?=\[Event)/);
  return chapterBlocks.map((block) => {
    const title = block.match(/\[ChapterName "(.*)"\]/)?.[1] || "Untitled";
    const url = block.match(/\[ChapterURL "(.*)"\]/)?.[1] || "";
    return { title, url, pgn: block.trim() };
  });
}

export function extractMovesWithComments(
  pgn: string
): { move: string; comment?: string }[] {
  const strippedHeaders = pgn.replace(/\[.*?\]\s*/g, "");
  const tokenRegex = /(\{[^}]*\})|(;[^\n]*)|([^\s{};]+)/g;
  const tokens = [...strippedHeaders.matchAll(tokenRegex)];

  const result: { move: string; comment?: string }[] = [];
  let currentComment: string | undefined = undefined;

  for (const match of tokens) {
    const token = match[0];
    if (token.startsWith("{")) {
      currentComment = token.slice(1, -1).trim();
    } else if (token.startsWith(";")) {
      currentComment = token.slice(1).trim();
    } else if (/^[a-hRNBQKO0-9+#=x-]+$/.test(token)) {
      result.push({ move: token, comment: currentComment });
      currentComment = undefined;
    }
  }

  return result;
}

export function extractGameInfo(pgn: string) {
  const info: Record<string, string> = {};
  const lines = pgn.split("\n");

  for (const line of lines) {
    const match = line.match(/\[(\w+)\s+"(.*)"\]/);
    if (match) {
      info[match[1]] = match[2];
    }
  }

  return info;
}

export function getValidGameId(url: string): string {
  if (!url) return "";

  try {
    const urlObj = new URL(url);
    const pathname = urlObj.pathname;
    const gameIdMatch = pathname.match(/^\/([a-zA-Z0-9]{8,12})(?:\/|$)/);

    if (gameIdMatch) {
      let gameId = gameIdMatch[1];
      if (gameId.length > 8) {
        gameId = gameId.substring(0, 8);
      }
      return gameId;
    }

    return "";
  } catch (error) {
    console.log(error);
    const parts = url.split("/");
    if (parts.length >= 4) {
      const gameId = parts[3];
      const cleanGameId = gameId.split(/[?#]/)[0];
      return cleanGameId.substring(0, 8);
    }

    return "";
  }
}

import { apiFetch } from '@/lib/api';

export async function fetchLichessGame(gameId: string): Promise<string> {
  const pgnText = await apiFetch<string>(`https://lichess.org/game/export/${gameId}`, {
    headers: {
      Accept: "application/x-chess-pgn",
    },
  });

  if (!pgnText || pgnText.trim() === "") {
    throw new Error("Empty PGN received from Lichess");
  }

  return pgnText;
}
