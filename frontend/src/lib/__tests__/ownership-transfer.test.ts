import { describe, it, expect } from 'vitest';
import {
  TERMINAL_STATES,
  TRANSFER_STATES,
  canConfirm,
  canRevoke,
  displayLabel,
  isExpiredByTime,
  isTerminal,
  nextActions,
} from '../ownership-transfer';

describe('TRANSFER_STATES', () => {
  it('lists all five states', () => {
    expect(TRANSFER_STATES).toEqual([
      'invite_pending',
      'accepted',
      'revoked',
      'expired',
      'completed',
    ]);
  });
});

describe('isTerminal', () => {
  it('returns true for terminal states', () => {
    expect(isTerminal('revoked')).toBe(true);
    expect(isTerminal('expired')).toBe(true);
    expect(isTerminal('completed')).toBe(true);
  });
  it('returns false for non-terminal states', () => {
    expect(isTerminal('invite_pending')).toBe(false);
    expect(isTerminal('accepted')).toBe(false);
  });
});

describe('canRevoke', () => {
  it('allows revoke from non-terminal pending states', () => {
    expect(canRevoke('invite_pending')).toBe(true);
    expect(canRevoke('accepted')).toBe(true);
  });
  it('blocks revoke from terminal states', () => {
    for (const s of TERMINAL_STATES) {
      expect(canRevoke(s)).toBe(false);
    }
  });
});

describe('canConfirm', () => {
  it('only allows confirm from accepted', () => {
    expect(canConfirm('accepted')).toBe(true);
    expect(canConfirm('invite_pending')).toBe(false);
    expect(canConfirm('revoked')).toBe(false);
    expect(canConfirm('expired')).toBe(false);
    expect(canConfirm('completed')).toBe(false);
  });
});

describe('displayLabel', () => {
  it('capitalises for UI per PRD §6', () => {
    expect(displayLabel('invite_pending')).toBe('Invite pending');
    expect(displayLabel('accepted')).toBe('Accepted');
    expect(displayLabel('revoked')).toBe('Revoked');
    expect(displayLabel('expired')).toBe('Expired');
    expect(displayLabel('completed')).toBe('Completed');
  });
});

describe('nextActions', () => {
  it('returns accept/revoke/wait for invite_pending', () => {
    expect(nextActions('invite_pending')).toEqual(['accept', 'revoke', 'wait']);
  });
  it('returns confirm/revoke for accepted', () => {
    expect(nextActions('accepted')).toEqual(['confirm', 'revoke']);
  });
  it('returns empty for terminal states', () => {
    expect(nextActions('revoked')).toEqual([]);
    expect(nextActions('expired')).toEqual([]);
    expect(nextActions('completed')).toEqual([]);
  });
});

describe('isExpiredByTime', () => {
  it('returns true when expires_at is in the past', () => {
    const past = new Date('2020-01-01T00:00:00Z').toISOString();
    expect(isExpiredByTime(past)).toBe(true);
  });
  it('returns false when expires_at is in the future', () => {
    const future = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
    expect(isExpiredByTime(future)).toBe(false);
  });
  it('returns false when expires_at is unparseable', () => {
    expect(isExpiredByTime('not-a-date')).toBe(false);
  });
  it('uses the supplied now reference', () => {
    const t = '2026-06-15T00:00:00Z';
    expect(isExpiredByTime(t, new Date('2026-06-14T00:00:00Z'))).toBe(false);
    expect(isExpiredByTime(t, new Date('2026-06-16T00:00:00Z'))).toBe(true);
  });
});
