import { createCollection } from '@tanstack/db';
import { powerSyncCollectionOptions } from '@tanstack/powersync-db-collection';
import type { AbstractPowerSyncDatabase } from '@powersync/web';
import { AppSchema } from './schema';

/**
 * Creates TanStack DB collections backed by a PowerSync database.
 * Call this once the PowerSync database has been initialized.
 */
export function createPowerSyncCollections(database: AbstractPowerSyncDatabase) {
  const userGames = createCollection(
    powerSyncCollectionOptions({
      database,
      table: AppSchema.props.user_games,
    }),
  );

  const repertoires = createCollection(
    powerSyncCollectionOptions({
      database,
      table: AppSchema.props.repertoires,
    }),
  );

  const repertoireNodes = createCollection(
    powerSyncCollectionOptions({
      database,
      table: AppSchema.props.repertoire_nodes,
    }),
  );

  const chatSessions = createCollection(
    powerSyncCollectionOptions({
      database,
      table: AppSchema.props.chat_sessions,
    }),
  );

  const userProgress = createCollection(
    powerSyncCollectionOptions({
      database,
      table: AppSchema.props.user_progress,
    }),
  );

  const courses = createCollection(
    powerSyncCollectionOptions({
      database,
      table: AppSchema.props.courses,
    }),
  );

  const puzzles = createCollection(
    powerSyncCollectionOptions({
      database,
      table: AppSchema.props.puzzles,
    }),
  );

  const lessons = createCollection(
    powerSyncCollectionOptions({
      database,
      table: AppSchema.props.lessons,
    }),
  );

  return {
    userGames,
    repertoires,
    repertoireNodes,
    chatSessions,
    userProgress,
    courses,
    puzzles,
    lessons,
  };
}

export type PowerSyncCollections = ReturnType<typeof createPowerSyncCollections>;
