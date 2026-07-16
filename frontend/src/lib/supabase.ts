import { createClient, type SupabaseClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

/**
 * Bare anon client. Unauthenticated reads only (RLS `anon` role).
 * Kept for existing imports — do NOT use for private Realtime channels.
 */
export const supabase = createClient(supabaseUrl, supabaseAnonKey);

/** Function signature matching Clerk's `getToken()`. */
export type GetTokenFn = () => Promise<string | null>;

/**
 * Clerk-authorized Supabase client (native third-party auth).
 *
 * `accessToken` is called by supabase-js on every request and for the Realtime
 * socket handshake, injecting the current Clerk JWT — which carries the
 * `role: authenticated` claim that our RLS + `realtime.messages` policies check.
 * This is what unlocks the private `game:{id}` broadcast/presence channels.
 *
 * Usage (client component):
 *   const { getToken } = useAuth();
 *   const sb = useMemo(() => createClerkSupabaseClient(getToken), [getToken]);
 *
 * For a private channel, also call `setRealtimeAuth(sb, token)` before
 * subscribing so the socket carries a fresh token (see below).
 */
export function createClerkSupabaseClient(getToken: GetTokenFn): SupabaseClient {
  return createClient(supabaseUrl, supabaseAnonKey, {
    accessToken: async () => (await getToken()) ?? null,
  });
}

/**
 * Push a fresh Clerk token onto the Realtime socket. Required before
 * subscribing to a private channel (`{ config: { private: true } }`) — the
 * broadcast/presence RLS policies run against this token, not the REST one.
 */
export async function setRealtimeAuth(
  client: SupabaseClient,
  getToken: GetTokenFn,
): Promise<void> {
  const token = await getToken();
  client.realtime.setAuth(token ?? undefined);
}
