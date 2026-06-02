// PRD §11.2 #7 — CSV bulk importer (Step 6).
//
// Pure utility module: header detection, row parsing, dedupe, validation.
// Component code calls these helpers; tests cover them without a DOM.

export interface CsvRow {
  email: string;
  first_name?: string;
  last_name?: string;
  raw: Record<string, string>;
}

export interface ColumnMapping {
  email: number | null;
  first_name: number | null;
  last_name: number | null;
  /** True when at least one heuristic matched; false ⇒ ask the user. */
  auto_detected: boolean;
}

export interface ValidatedRow {
  index: number;
  email: string;
  first_name?: string;
  last_name?: string;
  status: 'ok' | 'invalid' | 'duplicate';
  reason?: string;
}

// ── CSV parsing ──────────────────────────────────────────────────────────────

/**
 * Minimal CSV parser — handles quoted fields, escaped quotes ("") and
 * commas inside quotes. We do *not* ship a heavy lib for this — papaparse
 * adds ~50KB to the bundle and we only need a handful of features.
 */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let cur: string[] = [];
  let field = '';
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += ch;
      }
      continue;
    }
    if (ch === '"') {
      inQuotes = true;
      continue;
    }
    if (ch === ',') {
      cur.push(field);
      field = '';
      continue;
    }
    if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++;
      cur.push(field);
      field = '';
      rows.push(cur);
      cur = [];
      continue;
    }
    field += ch;
  }
  if (field.length || cur.length) {
    cur.push(field);
    rows.push(cur);
  }
  return rows.filter(r => r.some(c => c.trim().length > 0));
}

// ── Column mapping ───────────────────────────────────────────────────────────

const EMAIL_TOKENS = ['email', 'e-mail', 'mail'];
const FIRST_TOKENS = ['first name', 'firstname', 'given name', 'first'];
const LAST_TOKENS = ['last name', 'lastname', 'surname', 'family name', 'last'];
const FULL_NAME_TOKENS = ['name', 'full name', 'student name'];

function normaliseHeader(s: string): string {
  return s.toLowerCase().replace(/[\s_-]+/g, ' ').trim();
}

export function detectColumnMapping(headers: string[]): ColumnMapping {
  const norm = headers.map(normaliseHeader);
  const find = (tokens: string[]): number | null => {
    for (let i = 0; i < norm.length; i++) {
      if (tokens.includes(norm[i])) return i;
    }
    // Looser pass: substring match (avoid "email_address" failing equality)
    for (let i = 0; i < norm.length; i++) {
      if (tokens.some(t => norm[i].includes(t))) return i;
    }
    return null;
  };

  const email = find(EMAIL_TOKENS);
  let first = find(FIRST_TOKENS);
  let last = find(LAST_TOKENS);
  // Fallback: a single "Name" column maps to first_name.
  if (first == null && last == null) {
    const single = find(FULL_NAME_TOKENS);
    if (single != null && single !== email) first = single;
  }
  return {
    email,
    first_name: first,
    last_name: last,
    auto_detected: email != null,
  };
}

// ── Row mapping + validation ─────────────────────────────────────────────────

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export interface MappedImport {
  rows: ValidatedRow[];
  accepted_count: number;
  invalid_count: number;
  duplicate_count: number;
}

export function mapRows(
  data: string[][],
  mapping: ColumnMapping,
  existingEmails: string[] = [],
): MappedImport {
  if (!data.length) {
    return { rows: [], accepted_count: 0, invalid_count: 0, duplicate_count: 0 };
  }
  const seen = new Set(existingEmails.map(e => e.toLowerCase()));
  const result: ValidatedRow[] = [];
  let accepted = 0;
  let invalid = 0;
  let dup = 0;
  for (let i = 0; i < data.length; i++) {
    const r = data[i];
    const email = mapping.email != null ? (r[mapping.email] || '').trim() : '';
    const first =
      mapping.first_name != null ? (r[mapping.first_name] || '').trim() : '';
    const last =
      mapping.last_name != null ? (r[mapping.last_name] || '').trim() : '';

    const row: ValidatedRow = {
      index: i,
      email: email.toLowerCase(),
      first_name: first || undefined,
      last_name: last || undefined,
      status: 'ok',
    };
    if (!email || !EMAIL_RE.test(email)) {
      row.status = 'invalid';
      row.reason = 'Invalid email';
      invalid++;
    } else if (seen.has(email.toLowerCase())) {
      row.status = 'duplicate';
      row.reason = 'Duplicate email';
      dup++;
    } else {
      seen.add(email.toLowerCase());
      accepted++;
    }
    result.push(row);
  }
  return {
    rows: result,
    accepted_count: accepted,
    invalid_count: invalid,
    duplicate_count: dup,
  };
}

// ── Tier-cap-aware partition ─────────────────────────────────────────────────

export interface CapResult {
  to_import: ValidatedRow[];
  skipped_for_cap: ValidatedRow[];
}

export function applyTierCap(rows: ValidatedRow[], remainingSeats: number | null): CapResult {
  // null = unlimited (enterprise)
  if (remainingSeats == null) {
    return { to_import: rows.filter(r => r.status === 'ok'), skipped_for_cap: [] };
  }
  const okRows = rows.filter(r => r.status === 'ok');
  const cap = Math.max(0, remainingSeats);
  return {
    to_import: okRows.slice(0, cap),
    skipped_for_cap: okRows.slice(cap),
  };
}
