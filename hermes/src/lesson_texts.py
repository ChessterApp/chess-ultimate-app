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
EXPLANATION_CHAR_CAP = 3500  # of the lesson text handed to the model
MAX_DIAGRAMS = 4

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
    try:
        data = json.loads(PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — without the file the coach teaches as before
        logger.warning("lesson texts unavailable (%s)", PATH)
        return ()
    return tuple(r for r in data if isinstance(r, dict))


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
