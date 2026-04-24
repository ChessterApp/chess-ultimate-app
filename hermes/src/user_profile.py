"""User chess profile — Pydantic model + Supabase loader.

Stores per-user chess preferences and skill info for personalized coaching.
Profile is injected into the system prompt so the AI adapts to the student.
"""

import logging
import os
from typing import Optional

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class UserProfile(BaseModel):
    user_id: str
    rating: int = 1200
    goals: list[str] = Field(default_factory=list)
    preferred_openings: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    style: str = "unknown"

    def to_prompt_context(self) -> str:
        """Format the profile as context for the system prompt."""
        lines = [f"Student rating: {self.rating}"]
        if self.goals:
            lines.append(f"Goals: {', '.join(self.goals)}")
        if self.preferred_openings:
            lines.append(f"Preferred openings: {', '.join(self.preferred_openings)}")
        if self.weaknesses:
            lines.append(f"Known weaknesses: {', '.join(self.weaknesses)}")
        if self.style != "unknown":
            lines.append(f"Playing style: {self.style}")
        return "\n".join(lines)


def load_user_profile(
    user_id: str,
    supabase_url: str = None,
    supabase_key: str = None,
) -> UserProfile:
    """Load a user profile from Supabase. Returns defaults if not found."""
    url = supabase_url or os.environ.get("SUPABASE_URL", "")
    key = supabase_key or os.environ.get("SUPABASE_SERVICE_KEY", "")

    if not url or not key:
        logger.warning("Supabase not configured, returning default profile")
        return UserProfile(user_id=user_id)

    try:
        resp = httpx.get(
            f"{url}/rest/v1/user_profiles",
            params={"user_id": f"eq.{user_id}", "select": "*"},
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
            },
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        logger.exception("Failed to load user profile for %s", user_id)
        return UserProfile(user_id=user_id)

    if not rows:
        return UserProfile(user_id=user_id)

    row = rows[0]
    return UserProfile(
        user_id=user_id,
        rating=row.get("rating", 1200),
        goals=row.get("goals", []) or [],
        preferred_openings=row.get("preferred_openings", []) or [],
        weaknesses=row.get("weaknesses", []) or [],
        style=row.get("style", "unknown") or "unknown",
    )


def save_user_profile(
    profile: UserProfile,
    supabase_url: str = None,
    supabase_key: str = None,
) -> bool:
    """Save (upsert) a user profile to Supabase. Returns True on success."""
    url = supabase_url or os.environ.get("SUPABASE_URL", "")
    key = supabase_key or os.environ.get("SUPABASE_SERVICE_KEY", "")

    if not url or not key:
        logger.warning("Supabase not configured, cannot save profile")
        return False

    row = {
        "user_id": profile.user_id,
        "rating": profile.rating,
        "goals": profile.goals,
        "preferred_openings": profile.preferred_openings,
        "weaknesses": profile.weaknesses,
        "style": profile.style,
    }

    try:
        resp = httpx.post(
            f"{url}/rest/v1/user_profiles",
            json=row,
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception:
        logger.exception("Failed to save user profile for %s", profile.user_id)
        return False
