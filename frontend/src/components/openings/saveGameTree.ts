/**
 * saveGameTree — persists the edited move tree of an opened My Games tab.
 * Drafts (a fresh "Add variation" board) are created as a new game filed under
 * the active database; saved games are updated in place.
 */

import type { UserGame } from '@/hooks/useUserGames';
import type { OpenedGame } from './GameViewerPanel';
import type { AutoSaveEntry } from './useAutoSave';

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
    title: game.title ?? null,
    event: 'Variation',
    source: 'board_entry',
    database_id: databaseId ?? undefined,
  });
}

export interface TreeSnapshot {
  game: OpenedGame;
  pgn: string;
}

/**
 * What auto-save should persist for the open tree, or null when nothing should
 * be saved. Only own games (and drafts) are editable; an empty draft (no moves,
 * no title) is never created.
 */
export function treeAutoSaveEntry(
  game: OpenedGame | undefined,
  pgn: string,
  { hasMoves, isDirty }: { hasMoves: boolean; isDirty: boolean },
): AutoSaveEntry<TreeSnapshot> | null {
  if (!game || game.source !== 'user') return null;
  if (game.isDraft) {
    if (!hasMoves && !game.title) return null;
    return { key: `${game.title ?? ''}\n${pgn}`, value: { game, pgn } };
  }
  return isDirty ? { key: pgn, value: { game, pgn } } : null;
}

export interface TreeSaveOutcome {
  /** Tab id the save was made for (the draft id when it was just created). */
  oldId: string;
  /** Real game id; differs from oldId only when a draft was created. */
  newId: string;
  pgn: string;
}

/**
 * Builds the auto-save writer. A draft is created once; saves queued for it
 * afterwards (before the tab has taken over the real id) update that game.
 */
export function createTreeSaver(
  getDeps: () => SaveGameTreeDeps,
  onSaved: (outcome: TreeSaveOutcome) => void,
): (snapshot: TreeSnapshot) => Promise<boolean> {
  const createdIds = new Map<string, string>();
  return async ({ game, pgn }) => {
    const createdId = createdIds.get(game.id);
    const target = createdId ? { ...game, id: createdId, isDraft: undefined } : game;
    const result = await saveGameTree(target, pgn, getDeps());
    if (!result) return false;
    const newId = target.isDraft ? String(result.id) : target.id;
    if (target.isDraft) createdIds.set(game.id, newId);
    onSaved({ oldId: target.id, newId, pgn });
    return true;
  };
}

/**
 * Persists a renamed variation. Drafts keep the title in tab state; auto-save
 * creates the game with it, so only saved variations hit the update API.
 */
export async function saveVariationTitle(
  game: OpenedGame,
  title: string | null,
  updateGame: SaveGameTreeDeps['updateGame'],
): Promise<boolean> {
  if (game.isDraft) return true;
  return (await updateGame(game.id, { title })) !== null;
}
