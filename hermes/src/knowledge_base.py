"""Thematic knowledge base: the coach's topics (strategy, tactics, pawn structures,
typical positions, opening, middlegame, endgame) — section 1д of the brief.

Source of truth is YAML in ``hermes/content/topics/*.yaml`` (one list of topics
per section), versioned with the code and deployed by ``git pull``; no database
step. A topic carries a summary, key ideas, typical mistakes, Lichess puzzle
themes, ECO codes, lesson-title stems (to link the site's programme) and
positions given either as a FEN or as SAN moves from the start — the FEN is
computed here so authors never hand-type one. Everything is validated at load:
a malformed topic is logged and skipped, never served.

The same records can be mirrored into Supabase (``kb_topics`` / ``kb_positions``,
migration 019) with ``scripts/sync_kb_topics.py`` for the site and the mobile
app; the coach itself reads the YAML.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path
from typing import Optional

import chess
import yaml

logger = logging.getLogger(__name__)

PHASES = (
    "strategy", "tactics", "pawn_structure", "typical_position",
    "opening", "middlegame", "endgame",
)
PHASE_TITLES_RU = {
    "strategy": "Стратегия",
    "tactics": "Тактика",
    "pawn_structure": "Пешечные структуры",
    "typical_position": "Типовые позиции",
    "opening": "Дебют",
    "middlegame": "Миттельшпиль",
    "endgame": "Эндшпиль",
}
PHASE_TITLES_EN = {
    "strategy": "Strategy", "tactics": "Tactics", "pawn_structure": "Pawn structures",
    "typical_position": "Typical positions", "opening": "Opening",
    "middlegame": "Middlegame", "endgame": "Endgame",
}

_HERMES_ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = Path(os.environ.get("KB_TOPICS_DIR") or (_HERMES_ROOT / "content" / "topics"))

_lock = threading.Lock()
_cache: dict = {"dir": None, "mtime": None, "topics": None}


# ── Loading and validation ─────────────────────────────────────────────────


def _fen_from_moves(moves: str) -> tuple[str, list[str]]:
    board = chess.Board()
    san_list: list[str] = []
    for token in moves.replace("\n", " ").split():
        if re.fullmatch(r"\d+\.(\.\.)?", token) or token in ("1-0", "0-1", "1/2-1/2", "*"):
            continue
        token = re.sub(r"^\d+\.+", "", token)  # "10.Nxd4" → "Nxd4"
        if not token:
            continue
        move = board.parse_san(token)
        san_list.append(board.san(move))
        board.push(move)
    return board.fen(), san_list


def _normalise_position(pos: dict, topic_slug: str, index: int) -> Optional[dict]:
    """Return a validated position record or None (logged) if it is unusable."""
    if not isinstance(pos, dict):
        return None
    out = {
        "title_ru": str(pos.get("title_ru") or "").strip(),
        "title_en": str(pos.get("title_en") or "").strip(),
        "plan_ru": str(pos.get("plan_ru") or "").strip(),
        "best_move": str(pos.get("best_move") or "").strip() or None,
        "moves": None,
        "fen": None,
    }
    try:
        if pos.get("moves"):
            fen, san = _fen_from_moves(str(pos["moves"]))
            out["fen"] = fen
            out["moves"] = " ".join(
                f"{i // 2 + 1}.{m}" if i % 2 == 0 else m for i, m in enumerate(san)
            )
        elif pos.get("fen"):
            board = chess.Board(str(pos["fen"]).strip())
            if not board.is_valid():
                raise ValueError(f"invalid position: {board.status()!r}")
            out["fen"] = board.fen()
        else:
            raise ValueError("position needs moves or fen")
        if out["best_move"]:
            chess.Board(out["fen"]).parse_san(out["best_move"])  # must be legal
    except Exception as exc:  # noqa: BLE001 — bad content must not take the tool down
        logger.warning("kb topic %s position #%d skipped: %s", topic_slug, index, exc)
        return None
    out["side_to_move"] = "white" if chess.Board(out["fen"]).turn else "black"
    return out


def _as_str_list(value) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _normalise_topic(raw: dict, source: str) -> Optional[dict]:
    slug = str(raw.get("slug") or "").strip().lower()
    phase = str(raw.get("phase") or "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,60}", slug):
        logger.warning("kb topic in %s skipped: bad slug %r", source, raw.get("slug"))
        return None
    if phase not in PHASES:
        logger.warning("kb topic %s skipped: unknown phase %r", slug, phase)
        return None
    title_ru = str(raw.get("title_ru") or "").strip()
    if not title_ru:
        logger.warning("kb topic %s skipped: no title_ru", slug)
        return None
    try:
        level = int(raw.get("level") or 2)
    except (TypeError, ValueError):
        level = 2
    positions = []
    for i, pos in enumerate(raw.get("positions") or []):
        rec = _normalise_position(pos, slug, i)
        if rec:
            positions.append(rec)
    games = []
    for g in raw.get("model_games") or []:
        if isinstance(g, dict) and g.get("white") and g.get("black"):
            games.append({
                "white": str(g["white"]), "black": str(g["black"]),
                "year": g.get("year"), "note_ru": str(g.get("note_ru") or "").strip(),
            })
    return {
        "slug": slug,
        "phase": phase,
        "level": max(1, min(4, level)),
        "title_ru": title_ru,
        "title_en": str(raw.get("title_en") or "").strip(),
        "title_kk": str(raw.get("title_kk") or "").strip(),
        "summary_ru": " ".join(str(raw.get("summary_ru") or "").split()),
        "summary_en": " ".join(str(raw.get("summary_en") or "").split()),
        "summary_kk": " ".join(str(raw.get("summary_kk") or "").split()),
        "key_ideas_ru": _as_str_list(raw.get("key_ideas_ru")),
        "typical_mistakes_ru": _as_str_list(raw.get("typical_mistakes_ru")),
        "lichess_themes": _as_str_list(raw.get("lichess_themes")),
        "eco_codes": _as_str_list(raw.get("eco_codes")),
        "lesson_stems": [s.lower() for s in _as_str_list(raw.get("lesson_stems"))],
        "related": _as_str_list(raw.get("related")),
        # Extra search words a student may use for the topic ("греческий дар").
        "aliases": [a.lower() for a in _as_str_list(raw.get("aliases"))],
        "positions": positions,
        "model_games": games,
        "source": source,
    }


def _dir_mtime(directory: Path) -> Optional[float]:
    try:
        files = sorted(directory.glob("*.yaml"))
        if not files:
            return None
        return max(f.stat().st_mtime for f in files)
    except OSError:
        return None


def load_topics(directory: Optional[Path] = None, force: bool = False) -> dict[str, dict]:
    """slug → topic, in file order. Reloads when a YAML file changes on disk."""
    directory = Path(directory) if directory else CONTENT_DIR
    mtime = _dir_mtime(directory)
    with _lock:
        if (not force and _cache["topics"] is not None
                and _cache["dir"] == directory and _cache["mtime"] == mtime):
            return _cache["topics"]

    topics: dict[str, dict] = {}
    for path in sorted(directory.glob("*.yaml")) if directory.exists() else []:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        except Exception as exc:  # noqa: BLE001
            logger.error("kb file %s unreadable: %s", path.name, exc)
            continue
        if not isinstance(raw, list):
            logger.error("kb file %s must contain a list of topics", path.name)
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            topic = _normalise_topic(item, path.name)
            if topic is None:
                continue
            if topic["slug"] in topics:
                logger.warning("kb topic %s duplicated in %s; first definition kept", topic["slug"], path.name)
                continue
            topics[topic["slug"]] = topic
    with _lock:
        _cache.update({"dir": directory, "mtime": mtime, "topics": topics})
    if not topics:
        logger.warning("knowledge base is empty (looked in %s)", directory)
    return topics


def clear_cache() -> None:
    with _lock:
        _cache.update({"dir": None, "mtime": None, "topics": None})


# ── Lookup ─────────────────────────────────────────────────────────────────


def _norm(text: str) -> str:
    return re.sub(r"[^\w]+", " ", (text or "").lower(), flags=re.UNICODE).strip()


_QUERY_STOPWORDS = frozenset({
    "тема", "тему", "темы", "про", "о", "об", "что", "такое", "объясни", "расскажи", "как",
    "играть", "в", "на", "с", "и", "the", "a", "an", "what", "is", "explain", "about", "tell",
    "me", "topic", "туралы", "деген", "не", "қалай", "делать", "нужно", "надо", "можно", "мне",
    "почему", "когда", "покажи", "научи", "правильно", "должен", "should", "do", "i", "to",
})


def _stem_match(a: str, b: str) -> bool:
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 4 and long_.startswith(short[: max(4, len(short) - 1)])


def find_topics(query: str, topics: Optional[dict] = None, limit: int = 5) -> list[dict]:
    """Topics matching a slug, a title (any language), a Lichess theme or an ECO
    code, then by inflection-tolerant word overlap with titles and summaries."""
    topics = topics if topics is not None else load_topics()
    q = (query or "").strip().lower()
    if not q:
        return []
    exact = [t for t in topics.values() if t["slug"] == q or q in t["lichess_themes"]
             or q.upper() in t["eco_codes"] or q in t.get("aliases", [])]
    if exact:
        return exact[:limit]

    contains, scored = [], []
    q_tokens = [t for t in _norm(q).split() if t not in _QUERY_STOPWORDS]
    for t in topics.values():
        titles = [t["title_ru"].lower(), t["title_en"].lower(), t["title_kk"].lower(), *t.get("aliases", [])]
        if any(q in x for x in titles if x):
            contains.append(t)
            continue
        if not q_tokens:
            continue
        hay = set(_norm(" ".join(titles)).split())
        hay_wide = hay | set(_norm(t["summary_ru"] + " " + t["summary_en"]).split())
        hay_wide |= {s for s in t["lesson_stems"]} | {th.lower() for th in t["lichess_themes"]}
        title_hits = sum(1 for tok in q_tokens if any(_stem_match(tok, h) for h in hay))
        wide_hits = sum(1 for tok in q_tokens if any(_stem_match(tok, h) for h in hay_wide))
        score = title_hits * 3 + wide_hits
        # A title word counts three, a summary/theme word one; a topic needs the
        # equivalent of ~two-thirds of the query in its title to be a candidate,
        # so one shared word in a three-word question is not a match.
        if score >= 2 * len(q_tokens):
            scored.append((score, t))
    if contains:
        # The query is literally part of a title: that beats any word overlap.
        return contains[:limit]
    scored.sort(key=lambda s: -s[0])
    if scored and q_tokens and scored[0][0] >= 3 * len(q_tokens):
        scored = [s for s in scored if s[0] >= 3 * len(q_tokens)]
    return [t for _, t in scored][:limit]


def topics_for_theme(theme: str, topics: Optional[dict] = None) -> list[dict]:
    """Topics that list the given Lichess puzzle theme."""
    topics = topics if topics is not None else load_topics()
    return [t for t in topics.values() if theme in t["lichess_themes"]]


def title(topic: dict, locale: Optional[str]) -> str:
    loc = (locale or "ru").lower()
    if loc == "en" and topic.get("title_en"):
        return topic["title_en"]
    if loc in ("kz", "kk") and topic.get("title_kk"):
        return topic["title_kk"]
    return topic["title_ru"]


def summary(topic: dict, locale: Optional[str]) -> str:
    loc = (locale or "ru").lower()
    if loc == "en" and topic.get("summary_en"):
        return topic["summary_en"]
    if loc in ("kz", "kk") and topic.get("summary_kk"):
        return topic["summary_kk"]
    return topic["summary_ru"]
