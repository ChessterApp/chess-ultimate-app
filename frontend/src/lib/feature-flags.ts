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

export const LOCAL_FIRST_SUBSCRIPTION =
  process.env.NEXT_PUBLIC_LOCAL_FIRST_SUBSCRIPTION === 'true';

export const LOCAL_FIRST_CHAT =
  process.env.NEXT_PUBLIC_LOCAL_FIRST_CHAT === 'true';

export const ENHANCED_SW =
  process.env.NEXT_PUBLIC_ENHANCED_SW === 'true';

export const SMART_SERVICE_WORKER =
  process.env.NEXT_PUBLIC_SMART_SERVICE_WORKER === 'true';

export const PREFETCH_QUEUE =
  process.env.NEXT_PUBLIC_PREFETCH_QUEUE === 'true';

export const INSTANT_LOADING =
  process.env.NEXT_PUBLIC_INSTANT_LOADING === 'true';

export const SYNC_INDICATOR =
  process.env.NEXT_PUBLIC_SYNC_INDICATOR === 'true';

export const OFFLINE_MODE =
  process.env.NEXT_PUBLIC_OFFLINE_MODE === 'true';

/**
 * Online play (challenge-link live games). Gates the `/play/live/*` route and
 * the "Play a friend" entry UI. Off by default until the feature ships.
 */
export const ONLINE_PLAY_ENABLED =
  process.env.NEXT_PUBLIC_ONLINE_PLAY_ENABLED === 'true';
