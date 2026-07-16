/**
 * Realtime auth spike — Phase 1, Online Play.
 *
 * Proves the riskiest unknown of the whole feature: that the Clerk-authorized
 * Supabase client can reach the private Broadcast channel `game:{id}`, and that
 * non-players / anon are refused — enforced by the `realtime.messages` RLS
 * policies in supabase/migrations/20260716_026_online_play.sql.
 *
 * Run:
 *   cd frontend && npx tsx scripts/realtime-auth-spike.ts
 *
 * What runs automatically (no Clerk needed):
 *   1. Insert a test `games` row via the service-role key.
 *   2. Anon client subscribes to private `game:{id}` → asserts REJECTED.
 *   3. Cleanup (delete the test row).
 *
 * What needs a real Clerk token (Clerk cannot be minted headlessly — see the
 * doc block in the migration and docs/online-play-realtime-spike.md). Grab a
 * token in the browser devtools console while signed in:
 *     await window.Clerk.session.getToken()
 * then export it and re-run:
 *   SPIKE_PLAYER_TOKEN=<player's jwt>  \
 *   SPIKE_PLAYER_SUB=<player's clerk user id>  \
 *   SPIKE_NONPLAYER_TOKEN=<other user jwt>  \
 *   npx tsx scripts/realtime-auth-spike.ts
 * When those are set the spike additionally:
 *   4. Player client subscribes to `game:{id}`, broadcasts, asserts receipt.
 *   5. Non-player client subscribes to the same topic → asserts REJECTED.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { createClient, type SupabaseClient } from '@supabase/supabase-js';

// ── Minimal .env.local loader (no dependency) ────────────────────────────────
function loadEnv(): void {
  try {
    const raw = readFileSync(join(process.cwd(), '.env.local'), 'utf8');
    for (const line of raw.split('\n')) {
      const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
      if (!m) continue;
      const [, k, v] = m;
      if (!(k in process.env)) {
        process.env[k] = v.replace(/^["']|["']$/g, '');
      }
    }
  } catch {
    // ok if missing; rely on ambient env
  }
}
loadEnv();

const URL = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const ANON = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
const SERVICE = process.env.SUPABASE_SERVICE_ROLE_KEY!;
if (!URL || !ANON || !SERVICE) {
  console.error('Missing NEXT_PUBLIC_SUPABASE_URL / _ANON_KEY / SUPABASE_SERVICE_ROLE_KEY');
  process.exit(1);
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
let failures = 0;
function assert(ok: boolean, label: string) {
  console.log(`${ok ? '✅ PASS' : '❌ FAIL'}  ${label}`);
  if (!ok) failures++;
}

/**
 * Subscribe to a private channel and resolve how it settled.
 * 'SUBSCRIBED' = authorized; anything else within the window = rejected.
 */
function trySubscribe(
  client: SupabaseClient,
  topic: string,
  timeoutMs = 8000,
): Promise<{ status: string; channel: ReturnType<SupabaseClient['channel']> }> {
  return new Promise((resolve) => {
    const channel = client.channel(topic, { config: { private: true } });
    let settled = false;
    const done = (status: string) => {
      if (settled) return;
      settled = true;
      resolve({ status, channel });
    };
    channel.subscribe((status) => {
      if (status === 'SUBSCRIBED' || status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') {
        done(status);
      }
    });
    setTimeout(() => done('TIMED_OUT'), timeoutMs);
  });
}

async function main() {
  const admin = createClient(URL, SERVICE, { auth: { persistSession: false } });

  const playerSub = process.env.SPIKE_PLAYER_SUB ?? 'user_spike_player';
  const nonPlayerSub = process.env.SPIKE_NONPLAYER_SUB ?? 'user_spike_nonplayer';

  // 1. Insert a test game whose players are the (real, if provided) Clerk users.
  const { data: game, error: insErr } = await admin
    .from('games')
    .insert({
      creator_id: playerSub,
      opponent_id: nonPlayerSub === playerSub ? null : `user_spike_opponent`,
      white_id: playerSub,
      black_id: `user_spike_opponent`,
      status: 'active',
    })
    .select('id')
    .single();

  if (insErr || !game) {
    console.error('service-role insert failed:', insErr);
    process.exit(1);
  }
  const gameId = game.id as string;
  const topic = `game:${gameId}`;
  console.log(`\nSeeded test game ${gameId} (player=${playerSub})\n`);

  try {
    // 2. Anon must be refused on the private channel.
    const anon = createClient(URL, ANON, { auth: { persistSession: false } });
    const anonRes = await trySubscribe(anon, topic);
    assert(anonRes.status !== 'SUBSCRIBED', `anon REJECTED on ${topic} (got ${anonRes.status})`);
    await anon.removeAllChannels();

    // 4 & 5. Player / non-player assertions require real Clerk tokens.
    const playerToken = process.env.SPIKE_PLAYER_TOKEN;
    const nonPlayerToken = process.env.SPIKE_NONPLAYER_TOKEN;

    if (playerToken) {
      const player = createClient(URL, ANON, {
        auth: { persistSession: false },
        accessToken: async () => playerToken,
      });
      player.realtime.setAuth(playerToken);
      const pRes = await trySubscribe(player, topic);
      assert(pRes.status === 'SUBSCRIBED', `player SUBSCRIBED on ${topic} (got ${pRes.status})`);

      if (pRes.status === 'SUBSCRIBED') {
        let received = false;
        pRes.channel.on('broadcast', { event: 'ping' }, () => {
          received = true;
        });
        await pRes.channel.send({ type: 'broadcast', event: 'ping', payload: { t: 1 } });
        await wait(1500);
        assert(received, 'player received own broadcast on private channel');
      }
      await player.removeAllChannels();
    } else {
      console.log('⏭️  SKIP player-receives assertion — set SPIKE_PLAYER_TOKEN (see header).');
    }

    if (nonPlayerToken) {
      const nonPlayer = createClient(URL, ANON, {
        auth: { persistSession: false },
        accessToken: async () => nonPlayerToken,
      });
      nonPlayer.realtime.setAuth(nonPlayerToken);
      const npRes = await trySubscribe(nonPlayer, topic);
      assert(npRes.status !== 'SUBSCRIBED', `non-player REJECTED on ${topic} (got ${npRes.status})`);
      await nonPlayer.removeAllChannels();
    } else {
      console.log('⏭️  SKIP non-player-rejected assertion — set SPIKE_NONPLAYER_TOKEN (see header).');
    }
  } finally {
    // 3. Cleanup.
    await admin.from('games').delete().eq('id', gameId);
    console.log(`\nCleaned up test game ${gameId}`);
  }

  console.log(`\n${failures === 0 ? 'ALL ASSERTIONS PASSED' : `${failures} ASSERTION(S) FAILED`}`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
