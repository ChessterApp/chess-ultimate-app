"""
Puzzles API - Multi-puzzle lesson support
Endpoints for fetching and tracking progress on multiple puzzles within a lesson
"""

from flask import Blueprint, jsonify, request
from services.supabase_client import supabase
from utils.auth import verify_clerk_token, get_current_user_id
import logging
import time

logger = logging.getLogger(__name__)


def retry_supabase_query(query_func, max_retries=3, base_delay=0.5):
    """Execute a Supabase query with retry logic for transient connection errors."""
    last_error = None
    for attempt in range(max_retries):
        try:
            return query_func()
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            # Retry on connection-related errors
            if any(err in error_str for err in ['disconnected', 'connection', 'timeout', 'remoteprotocol']):
                delay = base_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(f"Supabase query failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                # Non-retryable error, raise immediately
                raise
    # All retries exhausted
    logger.error(f"Supabase query failed after {max_retries} attempts: {last_error}")
    raise last_error

puzzles_bp = Blueprint('puzzles', __name__)


@puzzles_bp.route('/api/learn/<course_slug>/<lesson_slug>/puzzles', methods=['GET'])
@verify_clerk_token
def get_lesson_puzzles(course_slug, lesson_slug):
    """
    Get all puzzles for a lesson with user progress.

    Returns:
        {
            "puzzles": [
                {
                    "id": "uuid",
                    "order_index": 1,
                    "fen": "...",
                    "solution_move": "e2e4",
                    "hint_text": "...",
                    "completed": true
                },
                ...
            ],
            "total_count": 10,
            "completed_count": 3,
            "current_index": 4  # Next uncompleted puzzle
        }
    """
    try:
        user_id = get_current_user_id()

        # Find lesson by slug
        lesson = _find_lesson_by_slugs(course_slug, lesson_slug)
        if not lesson:
            return jsonify({"error": "Lesson not found"}), 404

        lesson_id = lesson['id']

        # Check if lesson has multiple puzzles
        if not lesson.get('has_multiple_puzzles'):
            return jsonify({
                "puzzles": [],
                "total_count": 0,
                "completed_count": 0,
                "current_index": 0,
                "message": "This lesson does not have multiple puzzles"
            }), 200

        # Fetch puzzles for this lesson with retry
        puzzles_result = retry_supabase_query(
            lambda: supabase.table('lesson_puzzles')
                .select('*')
                .eq('lesson_id', lesson_id)
                .order('order_index')
                .execute()
        )

        puzzles = puzzles_result.data

        if not puzzles:
            return jsonify({
                "puzzles": [],
                "total_count": 0,
                "completed_count": 0,
                "current_index": 0
            }), 200

        # Get user progress for these puzzles with retry
        puzzle_ids = [p['id'] for p in puzzles]
        progress_result = retry_supabase_query(
            lambda: supabase.table('user_puzzle_progress')
                .select('puzzle_id, completed_at, attempts')
                .eq('user_id', user_id)
                .in_('puzzle_id', puzzle_ids)
                .execute()
        )

        # Create progress lookup
        progress_map = {}
        for prog in progress_result.data:
            progress_map[prog['puzzle_id']] = {
                'completed': prog.get('completed_at') is not None,
                'attempts': prog.get('attempts', 0)
            }

        # Enrich puzzles with progress
        completed_count = 0
        current_index = 1  # Default to first puzzle

        for puzzle in puzzles:
            prog = progress_map.get(puzzle['id'], {})
            puzzle['completed'] = prog.get('completed', False)
            puzzle['attempts'] = prog.get('attempts', 0)

            if puzzle['completed']:
                completed_count += 1
            elif current_index == 1 or current_index <= puzzle['order_index']:
                # Find first uncompleted puzzle
                if not puzzle['completed'] and current_index == 1:
                    current_index = puzzle['order_index']

        # Find actual current index (first uncompleted)
        for puzzle in puzzles:
            if not puzzle['completed']:
                current_index = puzzle['order_index']
                break
        else:
            # All completed, set to last puzzle
            current_index = len(puzzles)

        return jsonify({
            "puzzles": puzzles,
            "total_count": len(puzzles),
            "completed_count": completed_count,
            "current_index": current_index
        }), 200

    except Exception as e:
        logger.error(f"Error fetching puzzles: {e}", exc_info=True)
        return jsonify({"error": f"Failed to fetch puzzles: {str(e)}"}), 500


@puzzles_bp.route('/api/learn/<course_slug>/<lesson_slug>/puzzles/<int:puzzle_index>/complete', methods=['POST'])
@verify_clerk_token
def complete_puzzle(course_slug, lesson_slug, puzzle_index):
    """
    Mark a puzzle as completed.

    Args:
        puzzle_index: 1-based index of the puzzle in the lesson

    Request body (optional):
        {
            "attempts": 3  # Number of attempts before solving
        }

    Returns:
        {
            "success": true,
            "next_puzzle_index": 2,  # or null if lesson complete
            "lesson_complete": false
        }
    """
    try:
        user_id = get_current_user_id()
        data = request.get_json() or {}

        # Find lesson
        lesson = _find_lesson_by_slugs(course_slug, lesson_slug)
        if not lesson:
            return jsonify({"error": "Lesson not found"}), 404

        # Find puzzle by index
        puzzle_result = supabase.table('lesson_puzzles')\
            .select('*')\
            .eq('lesson_id', lesson['id'])\
            .eq('order_index', puzzle_index)\
            .execute()

        if not puzzle_result.data:
            return jsonify({"error": "Puzzle not found"}), 404

        puzzle = puzzle_result.data[0]

        # Update or insert progress
        progress_data = {
            'user_id': user_id,
            'puzzle_id': puzzle['id'],
            'completed_at': 'now()',
            'attempts': data.get('attempts', 1),
            'updated_at': 'now()'
        }

        supabase.table('user_puzzle_progress')\
            .upsert(progress_data, on_conflict='user_id,puzzle_id')\
            .execute()

        # Check if there's a next puzzle
        total_puzzles = lesson.get('puzzle_count', 0)
        next_index = puzzle_index + 1 if puzzle_index < total_puzzles else None
        lesson_complete = puzzle_index >= total_puzzles

        # If all puzzles complete, mark lesson as complete
        if lesson_complete:
            # Check if really all puzzles are complete
            all_puzzles = supabase.table('lesson_puzzles')\
                .select('id')\
                .eq('lesson_id', lesson['id'])\
                .execute()

            completed = supabase.table('user_puzzle_progress')\
                .select('puzzle_id')\
                .eq('user_id', user_id)\
                .in_('puzzle_id', [p['id'] for p in all_puzzles.data])\
                .not_.is_('completed_at', 'null')\
                .execute()

            if len(completed.data) >= len(all_puzzles.data):
                # Mark lesson as complete
                supabase.table('user_progress')\
                    .upsert({
                        'user_id': user_id,
                        'lesson_id': lesson['id'],
                        'status': 'completed',
                        'completed_at': 'now()',
                        'updated_at': 'now()'
                    }, on_conflict='user_id,lesson_id')\
                    .execute()

        return jsonify({
            "success": True,
            "next_puzzle_index": next_index,
            "lesson_complete": lesson_complete
        }), 200

    except Exception as e:
        logger.error(f"Error completing puzzle: {e}", exc_info=True)
        return jsonify({"error": f"Failed to complete puzzle: {str(e)}"}), 500


@puzzles_bp.route('/api/learn/<course_slug>/<lesson_slug>/puzzles/<int:puzzle_index>', methods=['GET'])
@verify_clerk_token
def get_single_puzzle(course_slug, lesson_slug, puzzle_index):
    """
    Get a single puzzle by index.

    Args:
        puzzle_index: 1-based index of the puzzle

    Returns:
        Puzzle object with progress
    """
    try:
        user_id = get_current_user_id()

        # Find lesson
        lesson = _find_lesson_by_slugs(course_slug, lesson_slug)
        if not lesson:
            return jsonify({"error": "Lesson not found"}), 404

        # Find puzzle
        puzzle_result = supabase.table('lesson_puzzles')\
            .select('*')\
            .eq('lesson_id', lesson['id'])\
            .eq('order_index', puzzle_index)\
            .execute()

        if not puzzle_result.data:
            return jsonify({"error": "Puzzle not found"}), 404

        puzzle = puzzle_result.data[0]

        # Get progress
        progress_result = supabase.table('user_puzzle_progress')\
            .select('*')\
            .eq('user_id', user_id)\
            .eq('puzzle_id', puzzle['id'])\
            .execute()

        if progress_result.data:
            prog = progress_result.data[0]
            puzzle['completed'] = prog.get('completed_at') is not None
            puzzle['attempts'] = prog.get('attempts', 0)
        else:
            puzzle['completed'] = False
            puzzle['attempts'] = 0

        # Add navigation info
        puzzle['total_count'] = lesson.get('puzzle_count', 0)
        puzzle['has_next'] = puzzle_index < puzzle['total_count']
        puzzle['has_prev'] = puzzle_index > 1

        return jsonify(puzzle), 200

    except Exception as e:
        logger.error(f"Error fetching puzzle: {e}", exc_info=True)
        return jsonify({"error": f"Failed to fetch puzzle: {str(e)}"}), 500


# Simple in-memory cache for lesson lookups
_lesson_cache = {}
_cache_ttl = 300  # 5 minutes


@puzzles_bp.route('/api/learn/<course_slug>/<lesson_slug>/puzzles/reset', methods=['POST'])
@verify_clerk_token
def reset_lesson_progress(course_slug, lesson_slug):
    """
    Reset all puzzle progress for a lesson.

    This clears:
    - All user_puzzle_progress entries for puzzles in this lesson
    - The user_progress entry for this lesson

    Returns:
        {
            "success": true,
            "puzzles_reset": 12,
            "message": "Progress reset successfully"
        }
    """
    try:
        user_id = get_current_user_id()

        # Find lesson
        lesson = _find_lesson_by_slugs(course_slug, lesson_slug)
        if not lesson:
            return jsonify({"error": "Lesson not found"}), 404

        lesson_id = lesson['id']

        # Get all puzzle IDs for this lesson
        puzzles_result = supabase.table('lesson_puzzles')\
            .select('id')\
            .eq('lesson_id', lesson_id)\
            .execute()

        puzzle_ids = [p['id'] for p in puzzles_result.data]
        puzzles_reset = 0

        # Delete puzzle progress entries
        if puzzle_ids:
            delete_result = supabase.table('user_puzzle_progress')\
                .delete()\
                .eq('user_id', user_id)\
                .in_('puzzle_id', puzzle_ids)\
                .execute()
            puzzles_reset = len(delete_result.data) if delete_result.data else 0

        # Reset lesson progress status
        supabase.table('user_progress')\
            .delete()\
            .eq('user_id', user_id)\
            .eq('lesson_id', lesson_id)\
            .execute()

        logger.info(f"Reset progress for user {user_id} on lesson {lesson_slug}: {puzzles_reset} puzzles")

        return jsonify({
            "success": True,
            "puzzles_reset": puzzles_reset,
            "message": "Progress reset successfully"
        }), 200

    except Exception as e:
        logger.error(f"Error resetting progress: {e}", exc_info=True)
        return jsonify({"error": f"Failed to reset progress: {str(e)}"}), 500


def _find_lesson_by_slugs(course_slug: str, lesson_slug: str):
    """
    Helper to find lesson by course and lesson slugs.
    Uses caching and optimized single-query lookup for fast performance.
    """
    import re

    cache_key = f"{course_slug}:{lesson_slug}"

    # Check cache first
    if cache_key in _lesson_cache:
        cached_data, cached_time = _lesson_cache[cache_key]
        if time.time() - cached_time < _cache_ttl:
            logger.debug(f"Cache hit for lesson: {cache_key}")
            return cached_data

    def generate_slug(title):
        slug = title.lower()
        slug = re.sub(r'\s+', '-', slug)
        slug = re.sub(r'[^a-z0-9-]', '', slug)
        slug = re.sub(r'-+', '-', slug)
        return slug.strip('-')

    # OPTIMIZED: Single query with joins instead of 3 sequential queries
    # NOTE: courses table does NOT have a slug column - we generate it from title
    try:
        # Try direct slug lookup first (single query)
        lesson_result = retry_supabase_query(
            lambda: supabase.table('lessons')
                .select('*, modules!inner(course_id, courses!inner(id, title))')
                .eq('slug', lesson_slug)
                .execute()
        )

        # Filter by course slug (generated from title)
        for lesson in lesson_result.data:
            module = lesson.get('modules', {})
            course = module.get('courses', {})
            c_slug = generate_slug(course.get('title', ''))
            if c_slug == course_slug:
                # Remove nested data, keep just lesson fields
                clean_lesson = {k: v for k, v in lesson.items() if k != 'modules'}
                _lesson_cache[cache_key] = (clean_lesson, time.time())
                logger.debug(f"Found lesson via direct slug lookup: {lesson_slug}")
                return clean_lesson
    except Exception as e:
        logger.debug(f"Direct slug lookup failed, trying fallback: {e}")

    # Fallback: title-based lookup if slug column doesn't exist or no match
    try:
        # Convert slug to title pattern (rook-checkmates -> %rook%checkmates%)
        title_pattern = '%' + '%'.join(lesson_slug.split('-')) + '%'

        lesson_result = retry_supabase_query(
            lambda: supabase.table('lessons')
                .select('*, modules!inner(course_id, courses!inner(id, title))')
                .ilike('title', title_pattern)
                .execute()
        )

        for lesson in lesson_result.data:
            module = lesson.get('modules', {})
            course = module.get('courses', {})
            c_slug = generate_slug(course.get('title', ''))
            l_slug = lesson.get('slug') or generate_slug(lesson.get('title', ''))

            if c_slug == course_slug and l_slug == lesson_slug:
                clean_lesson = {k: v for k, v in lesson.items() if k != 'modules'}
                _lesson_cache[cache_key] = (clean_lesson, time.time())
                logger.debug(f"Found lesson via title pattern: {lesson_slug}")
                return clean_lesson
    except Exception as e:
        logger.warning(f"Optimized query failed, using sequential fallback: {e}")

    # Ultimate fallback: original sequential method (should rarely hit this)
    logger.warning(f"Using slow sequential lookup for: {course_slug}/{lesson_slug}")

    courses_result = retry_supabase_query(
        lambda: supabase.table('courses').select('id, title').execute()
    )
    course = None
    for c in courses_result.data:
        c_slug = generate_slug(c.get('title', ''))
        if c_slug == course_slug:
            course = c
            break

    if not course:
        _lesson_cache[cache_key] = (None, time.time())
        return None

    modules_result = retry_supabase_query(
        lambda: supabase.table('modules')
            .select('id')
            .eq('course_id', course['id'])
            .execute()
    )

    if not modules_result.data:
        _lesson_cache[cache_key] = (None, time.time())
        return None

    module_ids = [m['id'] for m in modules_result.data]

    lessons_result = retry_supabase_query(
        lambda: supabase.table('lessons')
            .select('*')
            .in_('module_id', module_ids)
            .execute()
    )

    for lesson in lessons_result.data:
        l_slug = lesson.get('slug') or generate_slug(lesson.get('title', ''))
        if l_slug == lesson_slug:
            _lesson_cache[cache_key] = (lesson, time.time())
            return lesson

    _lesson_cache[cache_key] = (None, time.time())
    return None
