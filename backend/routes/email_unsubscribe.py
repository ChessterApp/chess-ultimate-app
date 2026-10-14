"""
One-click email unsubscribe (welcome drip, P4).

  GET|POST /api/email/unsubscribe?t=TOKEN

No auth — the HMAC-signed token (``services.welcome_drip``) is the proof.
GET is the footer link (returns a small page); POST is the RFC 8058
``List-Unsubscribe-Post`` one-click call from the mail client.
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from services import welcome_drip

logger = logging.getLogger(__name__)

email_unsubscribe_bp = Blueprint('email_unsubscribe', __name__)

_PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chesster</title></head>
<body style="margin:0;background:#f5f6f8;font-family:Arial,Helvetica,sans-serif;color:#1f2933;">
<div style="max-width:420px;margin:48px auto;padding:32px 24px;background:#ffffff;border-radius:12px;text-align:center;">
<img src="https://chesster.io/static/images/chesster-logo-v3.png" alt="Chesster" width="72" height="72">
<p style="font-size:18px;font-weight:bold;">You're unsubscribed.</p>
<p>Ты отписан(а) от рассылки.</p>
<p>Сен жазылымнан бас тарттың.</p>
<p style="margin-top:24px;"><a href="https://chesster.io" style="color:#2563eb;">chesster.io</a></p>
</div></body></html>"""


@email_unsubscribe_bp.route('/api/email/unsubscribe', methods=['GET', 'POST'])
def unsubscribe():
    email = welcome_drip.verify_unsubscribe_token(request.args.get('t'))
    if not email:
        return jsonify({'error': 'invalid token'}), 400
    try:
        welcome_drip.unsubscribe(email)
    except Exception:
        logger.exception('unsubscribe failed')
        return jsonify({'error': 'unsubscribe failed'}), 500
    if request.method == 'POST':
        return jsonify({'unsubscribed': True}), 200
    return _PAGE, 200, {'Content-Type': 'text/html; charset=utf-8'}
