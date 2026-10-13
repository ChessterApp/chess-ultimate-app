/**
 * Account-deletion manifest — the single, reviewable decision for every column
 * that holds a Clerk user id. `public.delete_user_data` (created in
 * `supabase/migrations/20261013_053_delete_user_data.sql`, last re-created in
 * `20261013_055_welcome_emails.sql`) implements exactly this; the manifest test keeps
 * the two in sync and fails when a migration adds a user-id column that has no
 * decision here.
 *
 *   DELETE_TABLES   — the person's rows are deleted.
 *   NULLIFY_COLUMNS — the shared row stays, the link to the person is set NULL.
 *   KEEP_COLUMNS    — retained on purpose (audit / billing), with the reason.
 *
 * Plain data + type annotations only: `scripts/check-user-data-coverage.mjs`
 * imports this file directly via Node's type stripping.
 */

export type DeleteTable = {
  table: string;
  /** Rows where ANY of these columns equals the user id are deleted. */
  columns: string[];
  /** Other user-id columns on the table that disappear with the deleted row. */
  alsoRemoves?: string[];
  /** Child table with no user column, deleted through its parent's rows. */
  via?: string;
};

export type ColumnDecision = { table: string; column: string; reason: string };

export const DELETE_TABLES: DeleteTable[] = [
  // Children before parents.
  { table: 'coach_messages', columns: [], via: 'coach_sessions.id = coach_messages.session_id' },
  { table: 'coach_sessions', columns: ['user_id'] },
  { table: 'analysis_chat_messages', columns: ['user_id'] },
  { table: 'analysis_conversations', columns: ['user_id'] },
  { table: 'user_games', columns: ['user_id'] },
  { table: 'user_game_collection_shares', columns: ['user_id'] },
  { table: 'user_shared_databases', columns: ['subscriber_id'] },
  { table: 'user_databases', columns: ['user_id'] },
  // Coach / AI telemetry.
  { table: 'api_usage', columns: ['user_id'] },
  { table: 'coach_bestofn_audit', columns: ['user_id'] },
  { table: 'coach_corrections', columns: ['user_id'] },
  { table: 'coach_curriculum', columns: ['user_id'] },
  { table: 'coach_curriculum_audit', columns: ['user_id'] },
  { table: 'coach_events', columns: ['user_id'] },
  { table: 'coach_feedback', columns: ['user_id'] },
  { table: 'coach_game_insights', columns: ['user_id'] },
  { table: 'coach_memory_audit', columns: ['user_id'] },
  { table: 'token_usage', columns: ['user_id'] },
  { table: 'voice_usage', columns: ['user_id'] },
  // Companion (task_attempt before task_assignment).
  { table: 'task_attempt', columns: ['owner_user_id'] },
  { table: 'task_assignment', columns: ['owner_user_id'] },
  { table: 'competency_evidence', columns: ['owner_user_id'] },
  { table: 'mastery_state', columns: ['owner_user_id'] },
  { table: 'quest_progress', columns: ['owner_user_id'] },
  { table: 'companion_weekly_goal', columns: ['owner_user_id'] },
  { table: 'domain_event', columns: ['owner_user_id'] },
  { table: 'companion', columns: ['owner_user_id'] },
  // Gameplay / learning.
  { table: 'lesson_chat_history', columns: ['user_id'] },
  { table: 'live_game_logs', columns: ['user_id'] },
  { table: 'opening_repertoires', columns: ['user_id'] },
  { table: 'player_ratings', columns: ['user_id'] },
  { table: 'player_fide_ratings', columns: ['user_id'] },
  { table: 'rating_history', columns: ['user_id'] },
  { table: 'puzzle_rush_bests', columns: ['user_id'] },
  { table: 'puzzle_rush_runs', columns: ['user_id'] },
  { table: 'puzzle_rush_school_pick', columns: ['user_id'] },
  { table: 'tournament_registrations', columns: ['user_id'] },
  { table: 'tournament_standings', columns: ['user_id'] },
  { table: 'user_progress', columns: ['user_id'] },
  { table: 'user_puzzle_progress', columns: ['user_id'] },
  // Identity / membership / linking.
  { table: 'family_link_invites', columns: ['inviter_user_id', 'accepted_by_user_id'] },
  { table: 'organization_ownership_transfers', columns: ['current_owner_user_id', 'invitee_user_id'] },
  { table: 'organization_members', columns: ['user_id'] },
  { table: 'link_attempts', columns: ['user_id'] },
  { table: 'pending_onboarding', columns: ['clerk_user_id'] },
  { table: 'platform_user_cache', columns: ['clerk_id'] },
  { table: 'platform_user_status', columns: ['clerk_id'] },
  // Welcome drip.
  { table: 'welcome_emails', columns: ['user_id'] },
  { table: 'email_opt_outs', columns: ['user_id'] },
  { table: 'subscriptions', columns: ['clerk_user_id'], alsoRemoves: ['whop_user_id'] },
  { table: 'user_onboarding', columns: ['clerk_user_id'] },
  { table: 'user_profiles', columns: ['user_id'] },
];

export const NULLIFY_COLUMNS: ColumnDecision[] = [
  { table: 'tournaments', column: 'created_by', reason: 'tournament is shared with every participant' },
  { table: 'tournament_games', column: 'white_player_id', reason: 'game is part of the opponent\'s and the tournament\'s history' },
  { table: 'tournament_games', column: 'black_player_id', reason: 'game is part of the opponent\'s and the tournament\'s history' },
  { table: 'branch_invite_tokens', column: 'created_by', reason: 'branch token is used by other students' },
  { table: 'wheel_presets', column: 'created_by', reason: 'preset is shared within the branch' },
  { table: 'organization_members', column: 'invited_by', reason: 'invited members keep their membership' },
  { table: 'pending_registrations', column: 'claimed_by_clerk_user_id', reason: 'registration belongs to the school roster' },
  { table: 'invite_jwts_consumed', column: 'clerk_user_id', reason: 'row must stay for JWT replay protection' },
];

export const KEEP_COLUMNS: ColumnDecision[] = [
  { table: 'platform_admin_audit_log', column: 'admin_clerk_id', reason: 'append-only admin audit log; DELETE is blocked by trigger' },
  { table: 'impersonation_sessions', column: 'admin_clerk_id', reason: 'admin security audit trail' },
  { table: 'impersonation_sessions', column: 'target_clerk_id', reason: 'admin security audit trail' },
  { table: 'organization_billing', column: 'whop_user_id', reason: 'org-level billing record, not personal data of the member' },
];

/** Column names that hold a Clerk (or provider) user id. */
const USER_ID_COLUMN = /^(user_id|clerk_user_id|clerk_id|owner_user_id|created_by|[a-z0-9_]+_user_id|[a-z0-9_]+_player_id|[a-z0-9_]+_clerk_id)$/;

export function isUserIdColumn(column: string): boolean {
  return USER_ID_COLUMN.test(column.toLowerCase());
}

/** `table.column` keys with a decision in the manifest. */
export function coveredColumns(): Set<string> {
  const keys = new Set<string>();
  for (const d of DELETE_TABLES) {
    for (const c of [...d.columns, ...(d.alsoRemoves ?? [])]) keys.add(`${d.table}.${c}`);
  }
  for (const d of [...NULLIFY_COLUMNS, ...KEEP_COLUMNS]) keys.add(`${d.table}.${d.column}`);
  return keys;
}

/** The user-id columns among `columns` that have no manifest decision. */
export function uncoveredUserIdColumns(columns: Array<{ table: string; column: string }>): string[] {
  const covered = coveredColumns();
  return columns
    .filter((c) => isUserIdColumn(c.column))
    .map((c) => `${c.table}.${c.column.toLowerCase()}`)
    .filter((key) => !covered.has(key));
}
