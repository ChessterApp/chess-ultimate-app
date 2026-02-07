"""
Opening Repertoire Service - Manages user's personal opening collections

Provides methods for:
- Fetching user's opening repertoire
- Adding openings to repertoire
- Updating opening notes and tags
- Removing openings from repertoire
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from services.supabase_client import supabase

logger = logging.getLogger(__name__)


class RepertoireService:
    """Service for managing user opening repertoires"""

    def __init__(self):
        """Initialize repertoire service with Supabase client"""
        self.db = supabase
        if self.db is None:
            logger.error("❌ Supabase client not initialized")
            raise RuntimeError("Supabase client not available")

    def get_user_repertoire(self, user_id: str, color: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all openings in user's repertoire, optionally filtered by color

        Args:
            user_id: The user's ID
            color: Optional filter - 'white', 'black', or 'all'

        Returns:
            List of opening repertoire entries
        """
        try:
            query = (
                self.db.table('user_opening_repertoire')
                .select('*')
                .eq('user_id', user_id)
            )

            if color and color != 'all':
                # Get openings for this color OR 'both'
                query = query.in_('color', [color, 'both'])

            result = query.order('created_at', desc=True).execute()
            logger.info(f"✅ Fetched {len(result.data)} repertoire openings for user {user_id}")
            return result.data

        except Exception as e:
            logger.error(f"❌ Error fetching repertoire for user {user_id}: {e}")
            raise

    def add_opening(
        self,
        user_id: str,
        opening_id: str,
        opening_name: str,
        color: str,
        eco_code: Optional[str] = None,
        first_moves: Optional[str] = None,
        notes: str = "",
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Add an opening to user's repertoire

        Args:
            user_id: The user's ID
            opening_id: Unique identifier for the opening
            opening_name: Human-readable opening name
            color: 'white', 'black', or 'both'
            eco_code: ECO classification code
            first_moves: Initial moves in PGN/SAN notation
            notes: User's notes about the opening
            tags: List of tags for organizing

        Returns:
            The created opening entry
        """
        try:
            data = {
                'user_id': user_id,
                'opening_id': opening_id,
                'opening_name': opening_name,
                'color': color,
                'eco_code': eco_code,
                'first_moves': first_moves,
                'notes': notes,
                'tags': tags or [],
                'favorite': False,
                'created_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat()
            }

            result = self.db.table('user_opening_repertoire').insert(data).execute()
            logger.info(f"✅ Added opening {opening_name} to repertoire for user {user_id}")
            return result.data[0]

        except Exception as e:
            logger.error(f"❌ Error adding opening to repertoire: {e}")
            raise

    def update_opening(
        self,
        user_id: str,
        opening_id: str,
        notes: Optional[str] = None,
        tags: Optional[List[str]] = None,
        favorite: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Update opening in user's repertoire

        Args:
            user_id: The user's ID
            opening_id: The opening's ID to update
            notes: Updated notes
            tags: Updated tags
            favorite: Favorite status

        Returns:
            The updated opening entry
        """
        try:
            update_data = {'updated_at': datetime.utcnow().isoformat()}

            if notes is not None:
                update_data['notes'] = notes
            if tags is not None:
                update_data['tags'] = tags
            if favorite is not None:
                update_data['favorite'] = favorite

            result = (
                self.db.table('user_opening_repertoire')
                .update(update_data)
                .eq('user_id', user_id)
                .eq('opening_id', opening_id)
                .execute()
            )

            if result.data:
                logger.info(f"✅ Updated opening {opening_id} for user {user_id}")
                return result.data[0]
            else:
                raise ValueError(f"Opening {opening_id} not found for user {user_id}")

        except Exception as e:
            logger.error(f"❌ Error updating opening: {e}")
            raise

    def delete_opening(self, user_id: str, opening_id: str) -> bool:
        """
        Remove opening from user's repertoire

        Args:
            user_id: The user's ID
            opening_id: The opening's ID to delete

        Returns:
            True if deletion was successful
        """
        try:
            result = (
                self.db.table('user_opening_repertoire')
                .delete()
                .eq('user_id', user_id)
                .eq('opening_id', opening_id)
                .execute()
            )

            logger.info(f"✅ Removed opening {opening_id} from repertoire for user {user_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error deleting opening: {e}")
            raise

    def add_variation(
        self,
        repertoire_id: str,
        variation_name: str,
        moves: str,
        notes: str = ""
    ) -> Dict[str, Any]:
        """
        Add a custom variation for an opening

        Args:
            repertoire_id: The repertoire entry ID
            variation_name: Name of the variation
            moves: Moves in PGN/SAN notation
            notes: Notes about the variation

        Returns:
            The created variation entry
        """
        try:
            data = {
                'repertoire_id': repertoire_id,
                'variation_name': variation_name,
                'moves': moves,
                'notes': notes,
                'created_at': datetime.utcnow().isoformat()
            }

            result = self.db.table('user_opening_variations').insert(data).execute()
            logger.info(f"✅ Added variation to repertoire {repertoire_id}")
            return result.data[0]

        except Exception as e:
            logger.error(f"❌ Error adding variation: {e}")
            raise

    def get_variations(self, repertoire_id: str) -> List[Dict[str, Any]]:
        """
        Get all variations for an opening

        Args:
            repertoire_id: The repertoire entry ID

        Returns:
            List of variation entries
        """
        try:
            result = (
                self.db.table('user_opening_variations')
                .select('*')
                .eq('repertoire_id', repertoire_id)
                .order('created_at', desc=True)
                .execute()
            )

            return result.data

        except Exception as e:
            logger.error(f"❌ Error fetching variations: {e}")
            raise


# Singleton instance
_repertoire_service = None


def get_repertoire_service() -> RepertoireService:
    """Get or create the repertoire service instance"""
    global _repertoire_service
    if _repertoire_service is None:
        _repertoire_service = RepertoireService()
    return _repertoire_service
