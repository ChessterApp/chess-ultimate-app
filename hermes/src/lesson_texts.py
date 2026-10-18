"""The programme's own words for the site's lessons (steps 1–3).

A lesson of the site carries a title, a video link and tasks — no explanation
(production, 2026-10-04: «Связка» is 85 characters, a heading and a YouTube
link). The client's course books («Ступени») have the explanation and the
diagrams. They live here, matched to the site's modules and lessons by lesson
id (and by course + module title as a fallback), so the coach teaches in the
programme's words and shows its diagrams while the site and its database stay
as they are. Built from the books on 2026-10-04 (ChessApp/stupeni-import).
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import chess

logger = logging.getLogger(__name__)

PATH = Path(__file__).resolve().parent.parent / "content" / "lessons" / "stupeni_steps_1-3.json"
# Steps 4–7 (16.10.2026): the site has no lessons for them — pawn structures and master games, the
# openings of steps 5 and 7, the endgames of step 6 — so they are the programme's own knowledge for
# «что такое открытая линия», «расскажи про шотландскую партию» (built by stupeni-import/build_steps_4-7.py).
PATHS = (PATH, PATH.with_name("stupeni_steps_4-7.json"))
EXPLANATION_CHAR_CAP = 3500  # of the lesson text handed to the model
MAX_DIAGRAMS = 4
SUMMARY_CHAR_CAP = 420

# «[Диаграмма s1_l8_theory_02.png: 6rk/6p1/7p/8/8/8/1B1Q4/7K w - - 0 1]» in the text
_MARKER = re.compile(r"\[Диаграмма\s+(?P<file>\S+?):\s*(?P<fen>[^\]]+)\]")


def _norm(text: Optional[str]) -> str:
    return re.sub(r"[^a-zа-я0-9]+", " ", (text or "").lower().replace("ё", "е")).strip()


def _legal(fen: str) -> bool:
    try:
        return bool(fen) and chess.Board(fen).is_valid()
    except (ValueError, IndexError):
        return False


@lru_cache(maxsize=1)
def _records() -> tuple:
    out: list[dict] = []
    for path in PATHS:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — without a file the coach teaches as before
            logger.warning("lesson texts unavailable (%s)", path)
            continue
        out += [r for r in data if isinstance(r, dict)]
    return tuple(out)


def clear_cache() -> None:
    _records.cache_clear()


def _find(lesson_id: Optional[str], course_slug: Optional[str], module_title: Optional[str],
          lesson_title: Optional[str]) -> Optional[dict]:
    recs = _records()
    if lesson_id:
        for r in recs:
            if any(l.get("lesson_id") == lesson_id for l in r.get("site_lessons") or []):
                return r
    if course_slug and module_title:
        key = _norm(module_title)
        for r in recs:
            if r.get("course_slug") == course_slug and _norm(r.get("module_title")) == key:
                return r
    if course_slug and lesson_title:
        key = _norm(lesson_title)
        for r in recs:
            if r.get("course_slug") == course_slug and any(_norm(l.get("title")) == key for l in r.get("site_lessons") or []):
                return r
    return None


def lesson_text(lesson_id: Optional[str] = None, course_slug: Optional[str] = None,
                module_title: Optional[str] = None, lesson_title: Optional[str] = None) -> Optional[dict]:
    """The programme's text and diagrams for a lesson of the site, or None.

    ``text``: the explanation (diagram markers kept as «[Диаграмма: FEN]» where
    the position is legal), ``diagrams``: legal explanatory positions with the
    phrase they illustrate, ``title``/``step``/``lesson``: where it comes from.
    """
    rec = _find(lesson_id, course_slug, module_title, lesson_title)
    if rec is None:
        return None
    return {
        "title": rec.get("docx_title"),
        "step": rec.get("docx_step"),
        "lesson": rec.get("docx_lesson"),
        "module": rec.get("module_title"),
        "course_slug": rec.get("course_slug"),
        "text": explanation(rec),
        "diagrams": diagrams(rec),
    }


def explanation(rec: dict, limit: int = EXPLANATION_CHAR_CAP) -> str:
    text = rec.get("text_ru") or ""

    def _mark(m: "re.Match") -> str:
        fen = m["fen"].strip()
        return f"[Диаграмма: {fen}]" if _legal(fen) else "[Диаграмма]"

    text = _MARKER.sub(_mark, text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > limit:
        cut = text.rfind(". ", 0, limit)
        text = text[: cut + 1 if cut > limit // 2 else limit].rstrip() + " …"
    return text


def diagrams(rec: dict) -> list[dict]:
    out: list[dict] = []
    for d in rec.get("diagrams") or []:
        fen = (d.get("fen") or "").strip()
        if d.get("valid") is False or not _legal(fen):
            continue  # a scheme without kings («how the rook moves») is not a position for the board
        out.append({"fen": fen, "context": (d.get("context") or "").strip()[:300]})
        if len(out) >= MAX_DIAGRAMS:
            break
    return out


# ── the programme's own topics (steps 4–7 and the titled lessons of 1–3), found by the student's words ──

_CONTINUATION = re.compile(r"\s*\((?:продолжение|окончание)\)\s*$", re.IGNORECASE)
_TITLE_NOISE = re.compile(r"[«»\"().!?,:;–—-]+")


_DIGIT_WORDS = (("2-х", "двух"), ("2х", "двух"), ("3-х", "трех"), ("4-х", "четырех"), ("1-й", "первый"))


def _title_key(rec: dict) -> str:
    title = _CONTINUATION.sub("", rec.get("docx_title") or "")
    for digits, word in _DIGIT_WORDS:
        title = title.replace(digits, word)
    return _norm(_TITLE_NOISE.sub(" ", title))


# Words that name no lesson by themselves («партия», «дебют», «эндшпиль»): dropped next to a real name
# («партия Ласкер — Томас»), and alone they find nothing («партия» is not «Шотландская партия»).
_GENERIC = frozenset({
    "партия", "партии", "партию", "партией", "урок", "уроки", "урока", "дебют", "дебюты", "дебюта", "эндшпиль",
    "эндшпиля", "гамбит", "защита", "защиты", "атака", "ход", "ходы", "позиция", "позиции", "пример", "примеры",
    "тренировка", "занятие", "продолжение", "техника", "расчет", "расчета", "белых", "черных", "чемпион", "мира",
    "game", "opening", "endgame", "lesson", "defense", "defence", "attack",
})


def _query_words(query: str) -> list[str]:
    from src.knowledge_base import _QUERY_STOPWORDS

    words = [w for w in _norm(query).split() if w not in _QUERY_STOPWORDS and len(w) >= 3]
    specific = [w for w in words if w not in _GENERIC]
    return specific  # nothing specific — nothing to find


def book_for_words(query: str) -> Optional[dict]:
    """The programme's lesson whose title is what the student named («открытая линия», «заколдованные
    квадраты», «шотландская партия», «Ласкер — Томас»), else None. Every word of the question that is
    not a stopword must be in the title (inflection-tolerant), so «партия» alone finds nothing; the
    first lesson of a series wins over its «(продолжение)» parts; a lesson with diagrams over one without.
    """
    from src.knowledge_base import _stem_match

    words = _query_words(query)
    if not words:
        return None
    best, best_score = None, None
    for rec in _records():
        title_words = _title_key(rec).split()
        if not title_words or not all(any(_stem_match(w, t) for t in title_words) for w in words):
            continue
        extra = _extra(title_words, words)
        if extra > 3:
            continue  # «партия» would match «Шотландская партия»… only by one word of five
        score = (
            -extra,
            0 if _CONTINUATION.search(rec.get("docx_title") or "") else 1,
            len(diagrams(rec)),
            -int(rec.get("docx_step") or 9),   # the earlier step first («Рокировка» of step 1, not step 6)
            len(rec.get("text_ru") or ""),
        )
        if best_score is None or score > best_score:
            best, best_score = rec, score
    return best


def _extra(title_words: list[str], query_words: list[str]) -> int:
    """How many words of the title the question did not name — generic words («партия», «гамбит») aside."""
    return max(0, len([t for t in title_words if t not in _GENERIC]) - len(query_words))


def book_title_extra(rec: dict, query: str) -> int:
    """How many words of the lesson's title the question did not name (0–1: the title itself)."""
    return _extra(_title_key(rec).split(), _query_words(query))


def book_series(rec: dict) -> list[dict]:
    """The lesson and its «(продолжение)» parts, in order (the same title, the same step)."""
    key = _title_key(rec)
    return [r for r in _records() if r.get("docx_step") == rec.get("docx_step") and _title_key(r) == key]


def book_view(rec: dict) -> dict:
    """The lesson as the coach's material: title, where it is in the programme, its text (with the
    diagram markers), its legal diagrams, the game it writes out (PGN) when it has one, its parts."""
    text = explanation(rec)
    series = book_series(rec)
    return {
        "source": "programme_book",
        "title": _CONTINUATION.sub("", (rec.get("docx_title") or "").strip()).rstrip(". "),
        "step": rec.get("docx_step"),
        "lesson": rec.get("docx_lesson"),
        "summary": _summary(text),
        "text": text,
        "diagrams": diagrams(rec),
        "pgn": rec.get("pgn"),
        "parts": [{"lesson": r.get("docx_lesson"), "title": (r.get("docx_title") or "").strip()}
                  for r in series if r is not rec],
        "site_lessons": [l for l in (rec.get("site_lessons") or []) if l.get("slug")],
    }


def _summary(text: str, limit: int = SUMMARY_CHAR_CAP) -> str:
    plain = re.sub(r"\[Диаграмма[^\]]*\]", " ", text)
    plain = re.sub(r"\s+", " ", plain).strip()
    if len(plain) <= limit:
        return plain
    cut = plain.rfind(". ", 0, limit)
    return plain[: cut + 1 if cut > limit // 2 else limit].rstrip() + " …"
