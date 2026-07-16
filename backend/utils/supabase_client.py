"""Shared Supabase client accessor.

Thin, lazily-importing wrapper around
``services.supabase_client.get_supabase_client`` so route/service modules can
obtain the singleton client without each re-defining the same three-line
``_get_supabase`` helper (previously copy-pasted across 19 modules). The
``services`` import is deferred to call time to avoid circular imports when this
module is imported from within the ``services`` package.
"""


def get_supabase():
    """Return the shared Supabase client (singleton)."""
    from services.supabase_client import get_supabase_client
    return get_supabase_client()
