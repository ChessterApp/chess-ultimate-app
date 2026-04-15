/**
 * Feature flags for progressive rollout of local-first architecture.
 * All flags default to false so nothing breaks in production.
 */

export const POWERSYNC_ENABLED =
  process.env.NEXT_PUBLIC_POWERSYNC_ENABLED === 'true';

export const LOCAL_FIRST_GAMES =
  process.env.NEXT_PUBLIC_LOCAL_FIRST_GAMES === 'true';

export const LOCAL_FIRST_REPERTOIRE =
  process.env.NEXT_PUBLIC_LOCAL_FIRST_REPERTOIRE === 'true';

export const ENHANCED_SW =
  process.env.NEXT_PUBLIC_ENHANCED_SW === 'true';

export const PREFETCH_QUEUE =
  process.env.NEXT_PUBLIC_PREFETCH_QUEUE === 'true';
