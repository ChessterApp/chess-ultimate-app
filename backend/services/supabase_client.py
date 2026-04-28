"""
Supabase Client - PostgreSQL Database Connection
Phase 1: Learning platform data (courses, lessons, progress, chat history)
Phase 1+: Organization / multi-tenant helpers
"""

import os
import logging
from supabase import create_client, Client
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Supabase credentials from environment
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

# Global Supabase client instance
supabase: Optional[Client] = None

def get_supabase_client() -> Client:
    """
    Get or create Supabase client instance.
    Returns singleton client for database operations.
    """
    global supabase

    if supabase is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise ValueError(
                "Missing Supabase credentials. "
                "Set SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables."
            )

        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        print(f"✅ Supabase client initialized: {SUPABASE_URL}")

    return supabase


# --- Organization helpers ---

def get_org_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """
    Lookup an organization by its subdomain slug.
    Returns the org dict or None if not found.
    """
    client = get_supabase_client()
    result = client.table('organizations').select('*').eq('slug', slug).eq('status', 'active').single().execute()
    return result.data if result.data else None


def get_org_members(org_id: str) -> List[Dict[str, Any]]:
    """
    Get all members of an organization.
    Returns a list of member dicts with user_id, role, joined_at.
    """
    client = get_supabase_client()
    result = client.table('organization_members').select('*').eq('organization_id', org_id).execute()
    return result.data or []


# Initialize client on import
try:
    supabase = get_supabase_client()
except Exception as e:
    print(f"⚠️  Warning: Could not initialize Supabase client: {e}")
    supabase = None
