/**
 * Ownership-transfer client helpers (PRD §11.3 #3).
 *
 * Pure helpers (no fetch) shipped here so route tests can target them
 * without spinning a JSDOM environment.
 */

export type TransferState =
  | 'invite_pending'
  | 'accepted'
  | 'revoked'
  | 'expired'
  | 'completed';

export const TRANSFER_STATES: TransferState[] = [
  'invite_pending',
  'accepted',
  'revoked',
  'expired',
  'completed',
];

export const TERMINAL_STATES: TransferState[] = ['revoked', 'expired', 'completed'];

export interface Transfer {
  id: string;
  organization_id: string;
  invitee_email: string;
  invitee_user_id?: string | null;
  state: TransferState;
  expires_at: string;
  accepted_at?: string | null;
  revoked_at?: string | null;
  completed_at?: string | null;
  created_at?: string;
}

export function isTerminal(state: TransferState): boolean {
  return TERMINAL_STATES.includes(state);
}

export function canRevoke(state: TransferState): boolean {
  return state === 'invite_pending' || state === 'accepted';
}

export function canConfirm(state: TransferState): boolean {
  return state === 'accepted';
}

export function displayLabel(state: TransferState): string {
  // PRD §6: API uses lowercase enum, UI capitalises
  return (
    {
      invite_pending: 'Invite pending',
      accepted: 'Accepted',
      revoked: 'Revoked',
      expired: 'Expired',
      completed: 'Completed',
    }[state] || state
  );
}

export function nextActions(state: TransferState): string[] {
  if (state === 'invite_pending') return ['accept', 'revoke', 'wait'];
  if (state === 'accepted') return ['confirm', 'revoke'];
  return [];
}

export function isExpiredByTime(
  expiresAt: string,
  now: Date = new Date(),
): boolean {
  const t = Date.parse(expiresAt);
  if (Number.isNaN(t)) return false;
  return t <= now.getTime();
}
