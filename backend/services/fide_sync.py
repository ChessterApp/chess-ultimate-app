"""
FIDE Rating Sync Service

Handles:
  - Linking a user to their FIDE ID
  - Fetching official FIDE ratings (placeholder)
  - Bulk import from FIDE published CSV list
"""

import csv
import logging
import re

logger = logging.getLogger(__name__)

FIDE_ID_PATTERN = re.compile(r'^\d{5,10}$')


def _get_supabase():
    """Lazy import to avoid circular imports at module level."""
    from services.supabase_client import get_supabase_client
    return get_supabase_client()


def link_fide_id(user_id: str, fide_id: str) -> dict:
    """
    Store or update a user's FIDE ID.
    Validates format: 5-10 digits.
    Returns the upserted row.
    """
    if not FIDE_ID_PATTERN.match(fide_id):
        raise ValueError(f'Invalid FIDE ID format: {fide_id}. Must be 5-10 digits.')

    supabase = _get_supabase()
    result = supabase.table('player_fide_ratings').upsert({
        'user_id': user_id,
        'fide_id': fide_id,
    }, on_conflict='user_id').execute()

    logger.info(f'Linked FIDE ID {fide_id} to user {user_id}')
    return result.data[0] if result.data else {}


def fetch_fide_rating(fide_id: str) -> dict | None:
    """
    Placeholder for fetching official FIDE rating data.
    In production this would call the FIDE API or scrape their site.
    Returns None for now.
    """
    logger.info(f'fetch_fide_rating called for {fide_id} (placeholder — returning None)')
    return None


def import_fide_csv(csv_path: str) -> int:
    """
    Bulk import player FIDE data from a FIDE published CSV list.

    Expected CSV columns (at minimum):
      fideid, name, federation, sex, title, w_title,
      o_title, foa_title, rating, games, k, rapid_rating,
      rapid_games, rapid_k, blitz_rating, blitz_games, blitz_k,
      birthday, flag

    Returns the number of rows imported.
    """
    supabase = _get_supabase()
    imported = 0

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        batch = []

        for row in reader:
            fide_id = row.get('fideid', '').strip()
            if not FIDE_ID_PATTERN.match(fide_id):
                continue

            standard = _parse_int(row.get('rating'))
            rapid = _parse_int(row.get('rapid_rating'))
            blitz = _parse_int(row.get('blitz_rating'))
            title = row.get('title', '').strip() or None
            federation = row.get('federation', '').strip() or None

            batch.append({
                'fide_id': fide_id,
                'standard_rating': standard,
                'rapid_rating': rapid,
                'blitz_rating': blitz,
                'title': title,
                'federation': federation,
            })

            if len(batch) >= 500:
                _upsert_fide_batch(supabase, batch)
                imported += len(batch)
                batch = []

        if batch:
            _upsert_fide_batch(supabase, batch)
            imported += len(batch)

    logger.info(f'Imported {imported} FIDE records from {csv_path}')
    return imported


def _upsert_fide_batch(supabase, batch: list):
    """Upsert a batch of FIDE records by fide_id."""
    supabase.table('player_fide_ratings').upsert(
        batch, on_conflict='fide_id'
    ).execute()


def _parse_int(value) -> int | None:
    """Safely parse an integer from a CSV field."""
    if value is None:
        return None
    try:
        v = int(str(value).strip())
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None
