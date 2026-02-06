"""
Photo to FEN API - Convert chessboard images to FEN notation

Uses OpenRouter's Gemini vision model to analyze chess board images
and extract FEN (Forsyth-Edwards Notation) strings.
"""

import os
import re
import logging
import requests
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

photo_fen_bp = Blueprint('photo_fen', __name__, url_prefix='/api')


@photo_fen_bp.route('/convert-image', methods=['POST'])
def convert_image_to_fen():
    """
    Convert a chessboard image to FEN notation.

    Expects JSON body with:
    - image: base64 encoded image string

    Returns:
    - fen: FEN string representation of the chess position
    """
    try:
        data = request.get_json()

        if not data or 'image' not in data:
            return jsonify({'error': 'No image provided'}), 400

        image_base64 = data['image']

        # Get OpenRouter API key
        openrouter_key = os.getenv('OPENROUTER_API_KEY')
        if not openrouter_key:
            logger.error("OPENROUTER_API_KEY not configured")
            return jsonify({'error': 'OpenRouter API key not configured'}), 500

        # Prepare the prompt for vision model
        prompt = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Analyze this chessboard image and output the FEN string. Only output the FEN string, nothing else. Make sure to correctly identify all pieces and their positions."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ]

        # Call OpenRouter API with vision model
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://chessempire.com",
                "X-Title": "Chess Empire - Photo to FEN"
            },
            json={
                "model": "google/gemini-3-flash-preview",  # Vision-capable model
                "messages": prompt
            },
            timeout=30
        )

        response_data = response.json()

        # Log usage for monitoring
        if response_data.get('usage'):
            logger.info(f"Photo-to-FEN token usage: {response_data['usage']}")

        if response.ok and response_data.get('choices'):
            fen_response = response_data['choices'][0]['message']['content'].strip()
            logger.info(f"Raw FEN response from model: {fen_response}")

            # Validate FEN format - should have at least 4 space-separated parts
            if len(fen_response.split(' ')) >= 4:
                logger.info(f"Returning FEN: {fen_response}")
                return jsonify({'fen': fen_response})

            # Try to extract FEN if model was verbose
            fen_pattern = r'([rnbqkpRNBQKP1-8]+\/){7}[rnbqkpRNBQKP1-8]+\s+[bw]\s+[KQkq-]+\s+[a-h1-8-]+\s+\d+\s+\d+'
            match = re.search(fen_pattern, fen_response)
            if match:
                return jsonify({'fen': match.group(0)})

            # If still no valid FEN, return error with response
            logger.warning(f"Invalid FEN response: {fen_response}")
            return jsonify({
                'error': 'Could not extract valid FEN from image analysis',
                'raw_response': fen_response
            }), 500
        else:
            error_msg = response_data.get('error', {}).get('message', 'Failed to analyze image')
            logger.error(f"OpenRouter API error: {error_msg}")
            return jsonify({'error': error_msg}), response.status_code or 500

    except requests.Timeout:
        logger.error("OpenRouter API timeout")
        return jsonify({'error': 'Image analysis timed out. Please try again.'}), 504
    except Exception as e:
        logger.error(f"Photo-to-FEN error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@photo_fen_bp.route('/convert-image/health', methods=['GET'])
def photo_fen_health():
    """Health check for photo-to-FEN service."""
    openrouter_key = os.getenv('OPENROUTER_API_KEY')
    return jsonify({
        'status': 'healthy' if openrouter_key else 'degraded',
        'openrouter_configured': bool(openrouter_key)
    })
