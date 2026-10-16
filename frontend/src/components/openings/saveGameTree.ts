/**
 * saveGameTree — persists the edited move tree of an opened My Games tab.
 * Drafts (a fresh "Add variation" board) are created as a new game filed under
 * the active database; saved games are updated in place.
 */

import type { UserGame } from '@/hooks/useUserGames';
import type { OpenedGame } from './GameViewerPanel';

type GameMetadata = Partial<Omit<UserGame, 'id' | 'user_id' | 'created_at' | 'updated_at'>>;

export interface SaveGameTreeDeps {
  databaseId: string | null;
  createGame: (pgn: string, metadata?: GameMetadata) => Promise<UserGame | null>;
  updateGame: (id: string, updates: GameMetadata) => Promise<UserGame | null>;
}

export async function saveGameTree(
  game: OpenedGame,
  pgn: string,
  { databaseId, createGame, updateGame }: SaveGameTreeDeps,
): Promise<UserGame | null> {
  if (!game.isDraft) return updateGame(game.id, { pgn });
  return createGame(pgn, {
    white: game.white,
    black: game.black,
    result: game.result,
    event: 'Variation',
    source: 'board_entry',
    database_id: databaseId ?? undefined,
  });
}
