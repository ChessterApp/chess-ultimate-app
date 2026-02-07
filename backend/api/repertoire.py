"""
Opening Repertoire API - User opening collection management

Endpoints for:
- GET /api/repertoire - Get user's opening repertoire
- POST /api/repertoire - Add opening to repertoire
- PUT /api/repertoire/{opening_id} - Update opening
- DELETE /api/repertoire/{opening_id} - Remove opening
- POST /api/repertoire/{repertoire_id}/variations - Add variation
- GET /api/repertoire/{repertoire_id}/variations - Get variations

All endpoints require Clerk authentication.
"""

import logging
from flask import Blueprint, request, jsonify

from utils.auth import verify_clerk_token, get_current_user_id
from services.repertoire_service import get_repertoire_service

logger = logging.getLogger(__name__)

# Create Blueprint
repertoire_bp = Blueprint('repertoire', __name__)

# Get service instance
def get_repertoire_service_instance():
    """Get repertoire service with error handling"""
    try:
        return get_repertoire_service()
    except RuntimeError as e:
        logger.error(f"❌ Repertoire service error: {e}")
        return None


@repertoire_bp.route('/api/repertoire', methods=['GET'])
@verify_clerk_token
def get_user_repertoire():
    """
    Get all openings in user's repertoire

    Query parameters:
    - color: Optional filter ('white', 'black', 'all')

    Returns:
        List of opening repertoire entries
    """
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        color_filter = request.args.get('color', 'all')
        service = get_repertoire_service_instance()

        if not service:
            return jsonify({'error': 'Service unavailable'}), 503

        repertoire = service.get_user_repertoire(user_id, color_filter if color_filter != 'all' else None)
        logger.info(f"✅ Fetched {len(repertoire)} openings for user {user_id}")
        return jsonify(repertoire), 200

    except Exception as e:
        logger.error(f"❌ Error fetching repertoire: {e}")
        return jsonify({'error': str(e)}), 500


@repertoire_bp.route('/api/repertoire', methods=['POST'])
@verify_clerk_token
def add_to_repertoire():
    """
    Add opening to user's repertoire

    Request body:
    {
        "opening_id": "string",
        "opening_name": "string",
        "color": "white|black|both",
        "eco_code": "string (optional)",
        "first_moves": "string (optional)",
        "notes": "string (optional)",
        "tags": ["string"] (optional)
    }

    Returns:
        The created opening entry
    """
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        # Validate required fields
        required_fields = ['opening_id', 'opening_name', 'color']
        missing_fields = [f for f in required_fields if f not in data]
        if missing_fields:
            return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400

        # Validate color
        if data['color'] not in ['white', 'black', 'both']:
            return jsonify({'error': 'Color must be "white", "black", or "both"'}), 400

        service = get_repertoire_service_instance()
        if not service:
            return jsonify({'error': 'Service unavailable'}), 503

        opening_entry = service.add_opening(
            user_id=user_id,
            opening_id=data['opening_id'],
            opening_name=data['opening_name'],
            color=data['color'],
            eco_code=data.get('eco_code'),
            first_moves=data.get('first_moves'),
            notes=data.get('notes', ''),
            tags=data.get('tags', [])
        )

        logger.info(f"✅ Added opening {data['opening_name']} to repertoire for user {user_id}")
        return jsonify(opening_entry), 201

    except Exception as e:
        logger.error(f"❌ Error adding opening to repertoire: {e}")
        return jsonify({'error': str(e)}), 500


@repertoire_bp.route('/api/repertoire/<opening_id>', methods=['PUT'])
@verify_clerk_token
def update_repertoire_opening(opening_id):
    """
    Update opening in user's repertoire

    Request body:
    {
        "notes": "string (optional)",
        "tags": ["string"] (optional),
        "favorite": boolean (optional)
    }

    Returns:
        The updated opening entry
    """
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        service = get_repertoire_service_instance()
        if not service:
            return jsonify({'error': 'Service unavailable'}), 503

        updated = service.update_opening(
            user_id=user_id,
            opening_id=opening_id,
            notes=data.get('notes'),
            tags=data.get('tags'),
            favorite=data.get('favorite')
        )

        logger.info(f"✅ Updated opening {opening_id} for user {user_id}")
        return jsonify(updated), 200

    except ValueError as e:
        logger.warning(f"⚠️  Opening not found: {e}")
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"❌ Error updating opening: {e}")
        return jsonify({'error': str(e)}), 500


@repertoire_bp.route('/api/repertoire/<opening_id>', methods=['DELETE'])
@verify_clerk_token
def remove_from_repertoire(opening_id):
    """
    Remove opening from user's repertoire

    Returns:
        Success message
    """
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        service = get_repertoire_service_instance()
        if not service:
            return jsonify({'error': 'Service unavailable'}), 503

        service.delete_opening(user_id, opening_id)
        logger.info(f"✅ Removed opening {opening_id} from repertoire for user {user_id}")
        return jsonify({'success': True}), 200

    except Exception as e:
        logger.error(f"❌ Error deleting opening: {e}")
        return jsonify({'error': str(e)}), 500


@repertoire_bp.route('/api/repertoire/<repertoire_id>/variations', methods=['POST'])
@verify_clerk_token
def add_variation(repertoire_id):
    """
    Add a custom variation for an opening

    Request body:
    {
        "variation_name": "string",
        "moves": "string",
        "notes": "string (optional)"
    }

    Returns:
        The created variation entry
    """
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        # Validate required fields
        required_fields = ['variation_name', 'moves']
        missing_fields = [f for f in required_fields if f not in data]
        if missing_fields:
            return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400

        service = get_repertoire_service_instance()
        if not service:
            return jsonify({'error': 'Service unavailable'}), 503

        variation = service.add_variation(
            repertoire_id=repertoire_id,
            variation_name=data['variation_name'],
            moves=data['moves'],
            notes=data.get('notes', '')
        )

        logger.info(f"✅ Added variation to repertoire {repertoire_id}")
        return jsonify(variation), 201

    except Exception as e:
        logger.error(f"❌ Error adding variation: {e}")
        return jsonify({'error': str(e)}), 500


@repertoire_bp.route('/api/repertoire/<repertoire_id>/variations', methods=['GET'])
@verify_clerk_token
def get_variations(repertoire_id):
    """
    Get all variations for an opening

    Returns:
        List of variation entries
    """
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        service = get_repertoire_service_instance()
        if not service:
            return jsonify({'error': 'Service unavailable'}), 503

        variations = service.get_variations(repertoire_id)
        return jsonify(variations), 200

    except Exception as e:
        logger.error(f"❌ Error fetching variations: {e}")
        return jsonify({'error': str(e)}), 500
