"""
Tiers API — canonical pricing/seat config served to the frontend.

GET /api/tiers — returns the full tier map from services.tier_quota.
Used by:
  - frontend/src/app/admin/billing/page.tsx (Plans grid)
  - frontend/src/app/for-schools/start/plan (wizard step 3)
"""

from flask import Blueprint, jsonify

from services.tier_quota import get_tiers

tiers_bp = Blueprint('tiers', __name__, url_prefix='/api')


@tiers_bp.route('/tiers', methods=['GET'])
def list_tiers():
    """Return the canonical tier map. Public — no auth required."""
    return jsonify({'tiers': get_tiers()})
