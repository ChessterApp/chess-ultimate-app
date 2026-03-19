"""
Lessons API - Phase 1
Endpoints for fetching courses, modules, and lessons
"""

from flask import Blueprint, jsonify, request
from services.supabase_client import supabase
from utils.auth import verify_clerk_token, get_current_user_id
from utils.cache import with_cache
from concurrent.futures import ThreadPoolExecutor
import time
import logging

logger = logging.getLogger(__name__)

lessons_bp = Blueprint('lessons', __name__)


def localize(obj, locale=None):
    """Apply localization to a DB object. Returns localized copy.
    For each field with a _{locale} variant, use the localized value if available.
    Falls back to English (original field) if translation is missing.
    """
    if not obj or not locale or locale == 'en':
        return obj
    result = dict(obj)
    # Preserve English-based slug before overwriting title with localized version
    if 'title' in result and not result.get('slug'):
        _t = result['title'].lower()
        _t = re.sub(r'\s+', '-', _t)
        _t = re.sub(r'[^a-z0-9-]', '', _t)
        _t = re.sub(r'-+', '-', _t).strip('-')
        result['slug'] = _t
    for field in ['title', 'description', 'content', 'hint_text', 'success_message']:
        localized_key = f'{field}_{locale}'
        if localized_key in result and result[localized_key]:
            result[field] = result[localized_key]
    return result


def localize_list(items, locale=None):
    """Apply localization to a list of DB objects."""
    if not locale or locale == 'en':
        return items
    return [localize(item, locale) for item in items]


def get_locale():
    """Get locale from query param or Accept-Language header."""
    locale = request.args.get('locale', '').strip().lower()
    if locale in ('ru', 'kk'):
        return locale
    # Check Accept-Language header
    accept = request.headers.get('Accept-Language', '')
    if 'ru' in accept:
        return 'ru'
    if 'kk' in accept:
        return 'kk'
    return 'en'

# Simple in-memory cache for course/lesson data (reduces Supabase round trips)
_cache = {
    'courses': None,
    'courses_time': 0,
    'lessons_by_course': {},  # course_id -> lessons list
    'lessons_time': {}  # course_id -> timestamp
}
CACHE_TTL = 300  # 5 minutes


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


def get_cached_courses():
    """Get courses with caching."""
    now = time.time()
    if _cache['courses'] and (now - _cache['courses_time']) < CACHE_TTL:
        return _cache['courses']

    result = retry_supabase_query(
        lambda: supabase.table('courses').select('*').execute()
    )
    _cache['courses'] = result.data
    _cache['courses_time'] = now
    return result.data


def get_cached_lessons_for_course(course_id):
    """Get all lessons for a course with caching."""
    now = time.time()
    if course_id in _cache['lessons_by_course']:
        if (now - _cache['lessons_time'].get(course_id, 0)) < CACHE_TTL:
            return _cache['lessons_by_course'][course_id]

    # Get modules for this course with retry
    modules_result = retry_supabase_query(
        lambda: supabase.table('modules').select('id').eq('course_id', course_id).execute()
    )
    if not modules_result.data:
        return []

    module_ids = [m['id'] for m in modules_result.data]

    # Get lessons for these modules with retry
    lessons_result = retry_supabase_query(
        lambda: supabase.table('lessons').select('*').in_('module_id', module_ids).execute()
    )

    _cache['lessons_by_course'][course_id] = lessons_result.data
    _cache['lessons_time'][course_id] = now
    return lessons_result.data


@lessons_bp.route('/api/courses', methods=['GET'])
@with_cache(max_age=300)
def get_courses():
    """
    Get all courses (public endpoint)

    Returns:
        [
            {
                "id": "uuid",
                "title": "Chess Fundamentals",
                "description": "Learn the basics...",
                "level": "beginner",
                "order_index": 1
            }
        ]
    """
    try:
        locale = get_locale()
        result = supabase.table('courses').select('*').order('order_index').execute()
        return jsonify(localize_list(result.data, locale)), 200
    except Exception as e:
        return jsonify({"error": f"Failed to fetch courses: {str(e)}"}), 500


@lessons_bp.route('/api/courses/<course_id>/modules', methods=['GET'])
@with_cache(max_age=300)
def get_course_modules(course_id):
    """
    Get all modules for a specific course

    Args:
        course_id: UUID of the course

    Returns:
        [
            {
                "id": "uuid",
                "course_id": "uuid",
                "title": "Tactical Motifs",
                "description": "Learn basic patterns",
                "order_index": 1
            }
        ]
    """
    try:
        locale = get_locale()
        result = supabase.table('modules')\
            .select('*')\
            .eq('course_id', course_id)\
            .order('order_index')\
            .execute()

        return jsonify(localize_list(result.data, locale)), 200
    except Exception as e:
        return jsonify({"error": f"Failed to fetch modules: {str(e)}"}), 500


# ============================================
# SLUG-BASED ENDPOINTS (SEO-friendly URLs)
# ============================================

import re

def generate_slug_from_title(title: str) -> str:
    """Generate a URL-friendly slug from a title."""
    slug = title.lower()
    slug = re.sub(r'\s+', '-', slug)
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug


def resolve_course_and_lesson(course_slug: str, lesson_slug: str = None):
    """
    Resolve course (and optionally lesson) from slugs.
    Supports both database slug fields and generated slugs from titles.
    Uses caching for faster lookups.

    Returns:
        (course, lesson) tuple, or (course, None) if lesson_slug not provided
        Returns (None, None) if not found
    """
    # Get courses from cache
    courses = get_cached_courses()

    course = None
    for c in courses:
        if c.get('slug') == course_slug or generate_slug_from_title(c.get('title', '')) == course_slug:
            course = c
            break

    if not course:
        return None, None

    if not lesson_slug:
        return course, None

    # Get lessons from cache
    lessons = get_cached_lessons_for_course(course['id'])

    lesson = None
    for l in lessons:
        if l.get('slug') == lesson_slug or generate_slug_from_title(l.get('title', '')) == lesson_slug:
            lesson = l
            break

    return course, lesson


@lessons_bp.route('/api/learn/<course_slug>', methods=['GET'])
@verify_clerk_token
def get_course_by_slug(course_slug):
    """
    Get course by slug (SEO-friendly URL)

    OPTIMIZED: Uses caching and parallel queries for faster response.

    Args:
        course_slug: URL-friendly slug (e.g., 'chess-fundamentals')

    Returns:
        Course object with modules, lessons, and progress
    """
    try:
        user_id = get_current_user_id()

        # OPTIMIZATION 1: Use cached courses instead of fresh query
        courses = get_cached_courses()

        # Find course by slug or by generated slug from title
        course = None
        for c in courses:
            if c.get('slug') == course_slug:
                course = c
                break
            # Fallback: generate slug from title and compare
            if generate_slug_from_title(c.get('title', '')) == course_slug:
                course = c
                break

        if not course:
            return jsonify({"error": "Course not found"}), 404

        course_id = course['id']

        # OPTIMIZATION 2: Fetch modules (still need fresh for ordering)
        modules_result = retry_supabase_query(
            lambda: supabase.table('modules')
                .select('*')
                .eq('course_id', course_id)
                .order('order_index')
                .execute()
        )
        modules = modules_result.data

        if not modules:
            return jsonify({
                "course": course,
                "modules": [],
                "lessons": {},
                "progress": {}
            }), 200

        module_ids = [m['id'] for m in modules]

        # OPTIMIZATION 3: Parallel fetch lessons and prepare for progress query
        def fetch_lessons():
            return retry_supabase_query(
                lambda: supabase.table('lessons')
                    .select('*')
                    .in_('module_id', module_ids)
                    .order('order_index')
                    .execute()
            )

        # Execute lessons query (progress query depends on lesson_ids, so can't fully parallelize)
        lessons_result = fetch_lessons()
        all_lessons = lessons_result.data

        # Group lessons by module_id
        lessons_by_module = {}
        lesson_ids = []
        for lesson in all_lessons:
            module_id = lesson['module_id']
            if module_id not in lessons_by_module:
                lessons_by_module[module_id] = []
            lessons_by_module[module_id].append(lesson)
            lesson_ids.append(lesson['id'])

        # Fetch progress (with retry)
        progress_map = {}
        if lesson_ids:
            # Capture lesson_ids in closure to avoid late binding
            ids_to_fetch = lesson_ids[:]
            progress_result = retry_supabase_query(
                lambda: supabase.table('user_progress')
                    .select('lesson_id, status, completed_at, started_at, time_spent_seconds, score')
                    .eq('user_id', user_id)
                    .in_('lesson_id', ids_to_fetch)
                    .execute()
            )
            if progress_result:
                for prog in progress_result.data:
                    progress_map[prog['lesson_id']] = {
                        'status': prog.get('status', 'not_started'),
                        'completed_at': prog.get('completed_at'),
                        'started_at': prog.get('started_at'),
                        'time_spent_seconds': prog.get('time_spent_seconds', 0),
                        'score': prog.get('score')
                    }

        locale = get_locale()
        # Localize lessons within each module group
        localized_lessons_by_module = {}
        for mod_id, mod_lessons in lessons_by_module.items():
            localized_lessons_by_module[mod_id] = localize_list(mod_lessons, locale)

        return jsonify({
            "course": localize(course, locale),
            "modules": localize_list(modules, locale),
            "lessons": localized_lessons_by_module,
            "progress": progress_map
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to fetch course: {str(e)}"}), 500


@lessons_bp.route('/api/learn/<course_slug>/<lesson_slug>', methods=['GET'])
@verify_clerk_token
def get_lesson_by_slug(course_slug, lesson_slug):
    """
    Get lesson by course and lesson slugs (SEO-friendly URL)
    Uses caching for faster lookups.

    Args:
        course_slug: URL-friendly course slug
        lesson_slug: URL-friendly lesson slug

    Returns:
        Lesson object with course context
    """
    try:
        user_id = get_current_user_id()

        # Use cached resolution for faster lookups
        course, lesson = resolve_course_and_lesson(course_slug, lesson_slug)

        if not course:
            return jsonify({"error": "Course not found"}), 404

        if not lesson:
            return jsonify({"error": "Lesson not found"}), 404

        # Check if lesson is locked
        if lesson.get('requires_lesson_id'):
            progress = supabase.table('user_progress')\
                .select('status')\
                .eq('user_id', user_id)\
                .eq('lesson_id', lesson['requires_lesson_id'])\
                .execute()

            if not progress.data or progress.data[0].get('status') != 'completed':
                # Get required lesson for redirect - use * to avoid slug column not existing
                required_lesson = supabase.table('lessons')\
                    .select('*')\
                    .eq('id', lesson['requires_lesson_id'])\
                    .execute()
                # Use db slug if available, otherwise generate from title
                required_slug = None
                if required_lesson.data:
                    req_lesson = required_lesson.data[0]
                    required_slug = req_lesson.get('slug') or generate_slug_from_title(req_lesson.get('title', ''))

                return jsonify({
                    "error": "Lesson locked",
                    "requires_lesson_slug": required_slug,
                    "course_slug": course_slug
                }), 403

        # Include course info in response
        locale = get_locale()
        localized_lesson = localize(lesson, locale)
        localized_course = localize(course, locale)
        localized_lesson['course_slug'] = course_slug
        localized_lesson['course_title'] = localized_course['title']

        return jsonify(localized_lesson), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to fetch lesson: {str(e)}"}), 500


@lessons_bp.route('/api/learn/<course_slug>/<lesson_slug>/progress', methods=['POST'])
@verify_clerk_token
def update_lesson_progress_by_slug(course_slug, lesson_slug):
    """
    Update lesson progress using slugs
    """
    try:
        user_id = get_current_user_id()
        data = request.get_json()

        # Resolve lesson using helper (supports both db slug and generated slug)
        course, lesson = resolve_course_and_lesson(course_slug, lesson_slug)

        if not course:
            return jsonify({"error": "Course not found"}), 404

        if not lesson:
            return jsonify({"error": "Lesson not found"}), 404

        lesson_id = lesson['id']

        # Build update object
        update_data = {
            'user_id': user_id,
            'lesson_id': lesson_id,
            'status': data.get('status', 'in_progress'),
            'updated_at': 'now()'
        }

        if 'time_spent_seconds' in data:
            update_data['time_spent_seconds'] = data['time_spent_seconds']

        if 'score' in data:
            update_data['score'] = data['score']

        if data.get('status') == 'in_progress':
            existing = retry_supabase_query(
                lambda: supabase.table('user_progress')
                    .select('started_at')
                    .eq('user_id', user_id)
                    .eq('lesson_id', lesson_id)
                    .execute()
            )

            if not existing.data or not existing.data[0].get('started_at'):
                update_data['started_at'] = 'now()'

        if data.get('status') == 'completed':
            update_data['completed_at'] = 'now()'

        result = retry_supabase_query(
            lambda: supabase.table('user_progress')
                .upsert(update_data, on_conflict='user_id,lesson_id')
                .execute()
        )

        return jsonify(result.data[0]), 200

    except Exception as e:
        return jsonify({"error": f"Failed to update progress: {str(e)}"}), 500


@lessons_bp.route('/api/learn/<course_slug>/<lesson_slug>/chat', methods=['GET', 'POST'])
@verify_clerk_token
def lesson_chat_by_slug(course_slug, lesson_slug):
    """
    Chat endpoint using slugs - redirects to existing chat logic
    """
    try:
        # Resolve lesson using helper (supports both db slug and generated slug)
        course, lesson = resolve_course_and_lesson(course_slug, lesson_slug)

        if not course:
            return jsonify({"error": "Course not found"}), 404

        if not lesson:
            return jsonify({"error": "Lesson not found"}), 404

        lesson_id = lesson['id']

        # Call existing chat functions with resolved lesson_id
        if request.method == 'GET':
            user_id = get_current_user_id()
            result = supabase.table('lesson_chat_history')\
                .select('messages')\
                .eq('user_id', user_id)\
                .eq('lesson_id', lesson_id)\
                .execute()

            if not result.data:
                return jsonify({"messages": []}), 200
            return jsonify(result.data[0]), 200

        else:  # POST
            user_id = get_current_user_id()
            data = request.get_json()
            user_message = data.get('message')

            if not user_message:
                return jsonify({"error": "Message is required"}), 400

            # Get lesson context
            lesson_full = supabase.table('lessons')\
                .select('*')\
                .eq('id', lesson_id)\
                .execute()

            lesson = lesson_full.data[0]
            lesson_content = lesson.get('content', '')
            lesson_title = lesson.get('title', '')

            # Get chat history
            history_result = supabase.table('lesson_chat_history')\
                .select('messages')\
                .eq('user_id', user_id)\
                .eq('lesson_id', lesson_id)\
                .execute()

            messages = history_result.data[0]['messages'] if history_result.data else []

            # Call LLM (using OpenRouter with Claude 3.5 Sonnet)
            try:
                import os
                from llm.openrouter_llm import OpenRouterLLM
                openrouter_key = os.getenv("OPENROUTER_API_KEY")
                llm = OpenRouterLLM(api_key=openrouter_key, model_name="anthropic/claude-3.5-sonnet")

                system_prompt = f"""You are a friendly and knowledgeable chess tutor helping a student with this lesson:

**Lesson: {lesson_title}**

{lesson_content}

Answer the student's questions about this lesson. Be encouraging, clear, and patient. Use examples when helpful."""

                # Build a prompt that includes conversation history
                conversation_context = ""
                for msg in messages:
                    role_label = "Student" if msg['role'] == 'user' else "Tutor"
                    conversation_context += f"{role_label}: {msg['content']}\n\n"

                # Add current user message
                full_prompt = f"{conversation_context}Student: {user_message}\n\nTutor:"

                response = llm.generate(
                    prompt=full_prompt,
                    system_message=system_prompt
                )
            except Exception as llm_error:
                logger.error(f"LLM error in lesson chat: {llm_error}", exc_info=True)
                response = f"I'm here to help with '{lesson_title}'. Please try again."

            messages.append({'role': 'user', 'content': user_message})
            messages.append({'role': 'assistant', 'content': response})

            supabase.table('lesson_chat_history')\
                .upsert({
                    'user_id': user_id,
                    'lesson_id': lesson_id,
                    'messages': messages,
                    'updated_at': 'now()'
                }, on_conflict='user_id,lesson_id')\
                .execute()

            return jsonify({'response': response, 'messages': messages}), 200

    except Exception as e:
        return jsonify({"error": f"Failed to process chat: {str(e)}"}), 500


@lessons_bp.route('/api/courses/<course_id>/full', methods=['GET'])
@verify_clerk_token
def get_course_full(course_id):
    """
    Get complete course data in a single request (optimized for performance).
    Fetches modules, lessons, and user progress with parallel queries.

    Args:
        course_id: UUID of the course

    Returns:
        {
            "modules": [...],
            "lessons": {"module_id": [...]},
            "progress": {"lesson_id": {...}}
        }
    """
    from concurrent.futures import ThreadPoolExecutor

    try:
        user_id = get_current_user_id()

        # Define fetch functions
        def fetch_modules():
            return supabase.table('modules')\
                .select('*')\
                .eq('course_id', course_id)\
                .order('order_index')\
                .execute()

        def fetch_all_lessons(module_ids):
            return supabase.table('lessons')\
                .select('*')\
                .in_('module_id', module_ids)\
                .order('order_index')\
                .execute()

        def fetch_all_progress(lesson_ids):
            if not lesson_ids:
                return None
            return supabase.table('user_progress')\
                .select('*')\
                .eq('user_id', user_id)\
                .in_('lesson_id', lesson_ids)\
                .execute()

        # Step 1: Fetch modules first (we need module_ids for lessons query)
        modules_result = fetch_modules()
        modules = modules_result.data

        if not modules:
            return jsonify({
                "modules": [],
                "lessons": {},
                "progress": {}
            }), 200

        module_ids = [m['id'] for m in modules]

        # Step 2: Fetch lessons (we need lesson_ids for progress query)
        lessons_result = fetch_all_lessons(module_ids)
        all_lessons = lessons_result.data

        # Group lessons by module_id and collect lesson IDs
        lessons_by_module = {}
        lesson_ids = []
        for lesson in all_lessons:
            module_id = lesson['module_id']
            if module_id not in lessons_by_module:
                lessons_by_module[module_id] = []
            lessons_by_module[module_id].append(lesson)
            lesson_ids.append(lesson['id'])

        # Step 3: Fetch progress
        progress_map = {}
        if lesson_ids:
            progress_result = fetch_all_progress(lesson_ids)
            if progress_result:
                for prog in progress_result.data:
                    progress_map[prog['lesson_id']] = {
                        'status': prog.get('status', 'not_started'),
                        'completed_at': prog.get('completed_at'),
                        'started_at': prog.get('started_at'),
                        'time_spent_seconds': prog.get('time_spent_seconds', 0),
                        'score': prog.get('score')
                    }

        return jsonify({
            "modules": modules,
            "lessons": lessons_by_module,
            "progress": progress_map
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to fetch course data: {str(e)}"}), 500


@lessons_bp.route('/api/modules/<module_id>/lessons', methods=['GET'])
@with_cache(max_age=300)
def get_module_lessons(module_id):
    """
    Get all lessons for a specific module

    Args:
        module_id: UUID of the module

    Returns:
        [
            {
                "id": "uuid",
                "module_id": "uuid",
                "title": "Introduction to Forks",
                "lesson_type": "theory",
                "order_index": 1
            }
        ]
    """
    try:
        result = supabase.table('lessons')\
            .select('*')\
            .eq('module_id', module_id)\
            .order('order_index')\
            .execute()

        return jsonify(result.data), 200
    except Exception as e:
        return jsonify({"error": f"Failed to fetch lessons: {str(e)}"}), 500


@lessons_bp.route('/api/lessons/<lesson_id>', methods=['GET'])
@verify_clerk_token
def get_lesson(lesson_id):
    """
    Get specific lesson content by ID (requires authentication)

    Args:
        lesson_id: UUID of the lesson

    Returns:
        {
            "id": "uuid",
            "title": "Introduction to Forks",
            "content": "# What is a Fork?...",
            "lesson_type": "theory",
            "exercise_fen": "...",
            "exercise_solution": [...]
        }
    """
    try:
        user_id = get_current_user_id()

        # Fetch lesson
        result = supabase.table('lessons')\
            .select('*')\
            .eq('id', lesson_id)\
            .execute()

        if not result.data:
            return jsonify({"error": "Lesson not found"}), 404

        lesson = result.data[0]

        # Check if lesson is locked (requires previous lesson completion)
        if lesson.get('requires_lesson_id'):
            # Check if user completed required lesson
            progress = supabase.table('user_progress')\
                .select('status')\
                .eq('user_id', user_id)\
                .eq('lesson_id', lesson['requires_lesson_id'])\
                .execute()

            if not progress.data or progress.data[0].get('status') != 'completed':
                return jsonify({
                    "error": "Lesson locked",
                    "requires_lesson_id": lesson['requires_lesson_id']
                }), 403

        return jsonify(lesson), 200

    except Exception as e:
        import traceback
        print(f"ERROR fetching lesson {lesson_id}: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Failed to fetch lesson: {str(e)}"}), 500


@lessons_bp.route('/api/lessons/<lesson_id>/progress', methods=['GET'])
@verify_clerk_token
def get_lesson_progress(lesson_id):
    """
    Get user's progress for a specific lesson

    Returns:
        {
            "status": "in_progress",
            "started_at": "2025-01-09T...",
            "time_spent_seconds": 120,
            "score": null
        }
    """
    try:
        user_id = get_current_user_id()

        result = supabase.table('user_progress')\
            .select('*')\
            .eq('user_id', user_id)\
            .eq('lesson_id', lesson_id)\
            .execute()

        if not result.data:
            # No progress yet - return default
            return jsonify({
                "status": "not_started",
                "started_at": None,
                "completed_at": None,
                "time_spent_seconds": 0,
                "score": None
            }), 200

        return jsonify(result.data[0]), 200

    except Exception as e:
        return jsonify({"error": f"Failed to fetch progress: {str(e)}"}), 500


@lessons_bp.route('/api/lessons/<lesson_id>/progress', methods=['POST'])
@verify_clerk_token
def update_lesson_progress(lesson_id):
    """
    Update user's progress for a specific lesson

    Request body:
        {
            "status": "in_progress" | "completed",
            "time_spent_seconds": 120,
            "score": 85  # Optional, for quiz/exercise lessons
        }

    Returns:
        Updated progress object
    """
    try:
        user_id = get_current_user_id()
        data = request.get_json()

        # Build update object
        update_data = {
            'user_id': user_id,
            'lesson_id': lesson_id,
            'status': data.get('status', 'in_progress'),
            'updated_at': 'now()'
        }

        # Add optional fields
        if 'time_spent_seconds' in data:
            update_data['time_spent_seconds'] = data['time_spent_seconds']

        if 'score' in data:
            update_data['score'] = data['score']

        # Set started_at if not started yet
        if data.get('status') == 'in_progress':
            # Check if progress exists
            existing = supabase.table('user_progress')\
                .select('started_at')\
                .eq('user_id', user_id)\
                .eq('lesson_id', lesson_id)\
                .execute()

            if not existing.data or not existing.data[0].get('started_at'):
                update_data['started_at'] = 'now()'

        # Set completed_at if completing
        if data.get('status') == 'completed':
            update_data['completed_at'] = 'now()'

        # Upsert progress
        result = supabase.table('user_progress')\
            .upsert(update_data, on_conflict='user_id,lesson_id')\
            .execute()

        return jsonify(result.data[0]), 200

    except Exception as e:
        return jsonify({"error": f"Failed to update progress: {str(e)}"}), 500


@lessons_bp.route('/api/lessons/<lesson_id>/chat', methods=['GET'])
@verify_clerk_token
def get_lesson_chat(lesson_id):
    """
    Get chat history for a specific lesson

    Returns:
        {
            "messages": [
                {"role": "user", "content": "What is a fork?"},
                {"role": "assistant", "content": "A fork is..."}
            ]
        }
    """
    try:
        user_id = get_current_user_id()

        result = supabase.table('lesson_chat_history')\
            .select('messages')\
            .eq('user_id', user_id)\
            .eq('lesson_id', lesson_id)\
            .execute()

        if not result.data:
            return jsonify({"messages": []}), 200

        return jsonify(result.data[0]), 200

    except Exception as e:
        return jsonify({"error": f"Failed to fetch chat history: {str(e)}"}), 500


@lessons_bp.route('/api/lessons/<lesson_id>/chat', methods=['POST'])
@verify_clerk_token
def send_lesson_chat(lesson_id):
    """
    Send a message to the AI tutor for this lesson

    Request body:
        {
            "message": "What is the best move in this position?"
        }

    Returns:
        {
            "response": "The best move is...",
            "messages": [...]  # Full chat history
        }
    """
    try:
        user_id = get_current_user_id()
        data = request.get_json()
        user_message = data.get('message')

        if not user_message:
            return jsonify({"error": "Message is required"}), 400

        # Get lesson context
        lesson_result = supabase.table('lessons')\
            .select('*')\
            .eq('id', lesson_id)\
            .execute()

        if not lesson_result.data:
            return jsonify({"error": "Lesson not found"}), 404

        lesson = lesson_result.data[0]
        lesson_content = lesson.get('content', '')
        lesson_title = lesson.get('title', '')

        # Get existing chat history
        history_result = supabase.table('lesson_chat_history')\
            .select('messages')\
            .eq('user_id', user_id)\
            .eq('lesson_id', lesson_id)\
            .execute()

        messages = history_result.data[0]['messages'] if history_result.data else []

        # Call LLM (using OpenRouter with Claude 3.5 Sonnet)
        try:
            import os
            from llm.openrouter_llm import OpenRouterLLM
            openrouter_key = os.getenv("OPENROUTER_API_KEY")
            llm = OpenRouterLLM(api_key=openrouter_key, model_name="anthropic/claude-3.5-sonnet")

            system_prompt = f"""You are a friendly and knowledgeable chess tutor helping a student with this lesson:

**Lesson: {lesson_title}**

{lesson_content}

Answer the student's questions about this lesson. Be encouraging, clear, and patient. Use examples when helpful."""

            # Prepare conversation context for LLM
            # Build a prompt that includes conversation history
            conversation_context = ""
            for msg in messages:
                role_label = "Student" if msg['role'] == 'user' else "Tutor"
                conversation_context += f"{role_label}: {msg['content']}\n\n"

            # Add current user message
            full_prompt = f"{conversation_context}Student: {user_message}\n\nTutor:"

            response = llm.generate(
                prompt=full_prompt,
                system_message=system_prompt
            )

        except Exception as llm_error:
            # Fallback to simple response if LLM fails
            response = f"I'm here to help with the lesson '{lesson_title}'. However, I'm having trouble processing your question right now. Please try again or rephrase your question."

        # Update chat history
        messages.append({'role': 'user', 'content': user_message})
        messages.append({'role': 'assistant', 'content': response})

        # Save to database
        supabase.table('lesson_chat_history')\
            .upsert({
                'user_id': user_id,
                'lesson_id': lesson_id,
                'messages': messages,
                'updated_at': 'now()'
            }, on_conflict='user_id,lesson_id')\
            .execute()

        return jsonify({
            'response': response,
            'messages': messages
        }), 200

    except Exception as e:
        return jsonify({"error": f"Failed to process chat message: {str(e)}"}), 500
