#!/usr/bin/env python3
"""
Backfill: register every existing org's `{slug}.chesster.io` with Vercel.

Walks `organizations` where the row is in a live state and the subdomain is
not yet active, then calls `add_domain` for each — idempotently handling
`domain_already_in_use`. Sleeps between rows for Vercel rate-limit safety.

CLI:
    python scripts/backfill_subdomains.py                # all stragglers
    python scripts/backfill_subdomains.py --dry-run      # report only
    python scripts/backfill_subdomains.py --slug SLUG    # one row

Run once after deploying the auto-registration code in onboarding.py — it
catches every org created before the wire-in.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone

# Make sibling backend modules importable when invoked as
# `python backend/scripts/backfill_subdomains.py` from repo root.
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(HERE)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

logger = logging.getLogger('backfill_subdomains')


def _load_env() -> None:
    """Best-effort load of backend/.env so VERCEL_TOKEN etc. resolve."""
    env_path = os.path.join(BACKEND_ROOT, '.env')
    if not os.path.exists(env_path):
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except Exception:
        # Fallback: parse KEY=VALUE lines manually.
        with open(env_path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _process_row(row: dict, *, dry_run: bool) -> str:
    from services.vercel_client import (
        VercelAPIError,
        get_client,
        subdomain_for_slug,
    )
    from services.supabase_client import get_supabase_client

    slug = row['slug']
    org_id = row['id']
    domain = subdomain_for_slug(slug)
    current = row.get('subdomain_status')

    if dry_run:
        logger.info('DRY-RUN org=%s slug=%s current=%s → would call add_domain(%s)',
                    org_id, slug, current, domain)
        return 'dry_run'

    client = get_client()
    update: dict = {}
    outcome: str

    try:
        result = client.add_domain(domain)
        vercel_id = result.get('id') or result.get('name') or domain
        update['subdomain_vercel_id'] = vercel_id
        if result.get('verified'):
            update['subdomain_status'] = 'active'
            update['subdomain_verified_at'] = datetime.now(timezone.utc).isoformat()
            outcome = 'active'
        else:
            update['subdomain_status'] = 'pending'
            outcome = 'pending'
        update['subdomain_last_error'] = None
    except VercelAPIError as exc:
        if exc.code == 'domain_already_in_use':
            # Idempotent: learn the current verified state from get_domain.
            try:
                live = client.get_domain(domain)
                vercel_id = live.get('id') or live.get('name') or domain
                update['subdomain_vercel_id'] = vercel_id
                if live.get('verified'):
                    update['subdomain_status'] = 'active'
                    update['subdomain_verified_at'] = datetime.now(timezone.utc).isoformat()
                    outcome = 'ok (active)'
                else:
                    update['subdomain_status'] = 'pending'
                    outcome = 'ok (pending)'
                update['subdomain_last_error'] = None
            except VercelAPIError as get_exc:
                update['subdomain_status'] = 'failed'
                update['subdomain_last_error'] = f'idempotent get_domain failed: {get_exc}'
                outcome = f'failed: {get_exc}'
        else:
            update['subdomain_status'] = 'failed'
            update['subdomain_last_error'] = str(exc)
            outcome = f'failed: {exc}'
    except Exception as exc:
        update['subdomain_status'] = 'failed'
        update['subdomain_last_error'] = f'unexpected: {exc}'
        outcome = f'failed: {exc}'

    supabase = get_supabase_client()
    supabase.table('organizations').update(update).eq('id', org_id).execute()
    logger.info(
        'org=%s slug=%s → status=%s outcome=%s',
        org_id, slug, update.get('subdomain_status'), outcome,
    )
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true',
                        help='Log what would happen without calling Vercel or updating DB.')
    parser.add_argument('--slug', help='Process only the given slug.')
    parser.add_argument('--sleep', type=float, default=0.5,
                        help='Seconds to sleep between rows (default 0.5).')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
    )

    _load_env()
    from services.supabase_client import get_supabase_client

    supabase = get_supabase_client()
    query = (
        supabase.table('organizations')
        .select('id, slug, subdomain_status, status, deletion_requested_at')
        .in_('status', ['trial', 'active'])
        .is_('deletion_requested_at', 'null')
    )
    if args.slug:
        query = query.eq('slug', args.slug)
    rows = (query.execute().data or [])

    eligible = [
        r for r in rows
        if r.get('slug') and (r.get('subdomain_status') in (None, 'pending', 'verifying', 'failed'))
    ]
    if args.slug and not eligible and rows:
        # Even if status is already 'active', honor explicit --slug for visibility.
        eligible = [r for r in rows if r.get('slug') == args.slug]

    logger.info('candidates=%d (slug-filter=%s, dry-run=%s)', len(eligible), args.slug, args.dry_run)
    if not eligible:
        logger.info('nothing to do')
        return 0

    failed = 0
    for row in eligible:
        try:
            outcome = _process_row(row, dry_run=args.dry_run)
            if outcome.startswith('failed'):
                failed += 1
        except Exception as exc:
            failed += 1
            logger.exception('row processing crashed for slug=%s: %s', row.get('slug'), exc)
        time.sleep(args.sleep)

    logger.info('done: total=%d failed=%d', len(eligible), failed)
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
