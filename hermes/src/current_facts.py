"""The current state of the chess world, fetched now — not remembered (2026-10-20).

Alexander's screenshot (20.10): the voice coach said «загуглил, проверил ещё раз: чемпион мира — Дин Лижэнь»
— it had not searched anything, its training data simply ends before Gukesh won (December 2024), and the
text coach (DeepSeek) invents details the same way («в 2025-м защитил звание»). Neither model has live
internet, and the old search_web asked DuckDuckGo's instant answers, which have nothing on such questions.

Now a question about the current state — the world champion (men's, women's), the top of the rating
list, the last championship or Candidates — is recognised by its words, the relevant Wikipedia article's
introduction is fetched (English and Russian, cached for a few hours) and goes to the model as a
«Verified current facts» block with the date; the voice coach gets the same through the `current_facts`
tool (POST /api/coach/voice/intent says `fact`, the site calls the tool). When Wikipedia is unreachable,
a short list of facts known for certain, with its own date, goes in instead — and the coach is told to
say which date its answer is from. The prompts say plainly: no live internet, never claim to have googled.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TIMEOUT_S = 4.0
CACHE_TTL_S = 6 * 3600
MAX_CHARS = 1200

# Questions about the present: «кто сейчас чемпион мира», «действующий чемпион», «кто первый в рейтинге»,
# «кто выиграл турнир претендентов», "who is the world champion", «әлем чемпионы кім».
_ASKS = re.compile(
    r"(?<![\w-])(?:чемпион\w*\s+мира|чемпион\w*\s+(?:по\s+)?шахмат\w*|действующ\w+\s+чемпион\w*|нынешн\w+\s+чемпион\w*|"
    r"текущ\w+\s+чемпион\w*|(?:кто|какой)\s+(?:сейчас\s+|сегодня\s+)?чемпион\w*|чемпионк\w*\s+мира|"
    r"перв\w+\s+(?:(?:номер\w*|строчк\w*|мест\w*)\s+)?(?:в\s+)?(?:мирово\w+\s+)?рейтинг\w*|лидер\w*\s+рейтинг\w*|"
    r"рейтинг\w*\s+(?:фиде|fide)|сильнейш\w+\s+шахматист\w*\s+(?:мира|сейчас|сегодня|планеты)|"
    r"лучш\w+\s+шахматист\w*\s+(?:мира|сейчас|сегодня|планеты)|турнир\w*\s+претендент\w*|претендент\w*\s+на\s+(?:титул|корону)|"
    r"матч\w*\s+(?:на\s+)?(?:первенств\w+|звание)\s+(?:мира|чемпиона)|последн\w+\s+чемпионат\w*\s+мира|"
    r"world\s+(?:chess\s+)?champion(?:ship)?|women'?s\s+world\s+champion|(?:top|number\s+one|#1)\s+(?:rated\s+)?(?:player|in\s+the\s+world)|"
    r"fide\s+(?:rating|ranking)s?|candidates\s+tournament|әлем\s+чемпион\w*|чемпион\w*\s+әлем\w*|рейтинг\s+көшбасшы\w*)(?![\w-])",
    re.IGNORECASE)
_WOMEN = re.compile(r"чемпионк|женск|among\s+women|women|әйел", re.IGNORECASE)
_RATING = re.compile(r"рейтинг|сильнейш|лучш\w+\s+шахматист|rated|ranking|number\s+one|#1|top\s+player|көшбасшы", re.IGNORECASE)
_CANDIDATES = re.compile(r"претендент|candidates", re.IGNORECASE)

# Wikipedia articles whose introduction states the current holder (English first: its first paragraph
# names the champion; the Russian one adds the words the coach answers in), and the event whose newest
# year page says what happened last (the 2026 match page: «upcoming … Gukesh against Sindarov, the winner
# of the Candidates Tournament 2026» — the general pages' introductions do not say this).
PAGES = {
    "champion": [("en", "World Chess Championship"), ("ru", "Чемпионат мира по шахматам")],
    "women": [("en", "Women's World Chess Championship"), ("en", "Ju Wenjun")],
    "rating": [("en", "FIDE rankings"), ("ru", "Рейтинг ФИДЕ")],
    "candidates": [("en", "Candidates Tournament"), ("ru", "Турнир претендентов")],
}
EVENT = {  # the base title of the year pages, English
    "champion": "World Chess Championship",
    "women": "Women's World Chess Championship",
    "candidates": "Candidates Tournament",
}

# Known for certain when this was written; the date goes into the answer when Wikipedia is unreachable.
FALLBACK_AS_OF = "2026-10-20"
FALLBACK = {
    "champion": ("Classical world champion: Gukesh Dommaraju (India) — he beat Ding Liren 7.5–6.5 in the 2024 World "
                 "Championship match in Singapore (December 2024) and holds the title since. His next title match, the "
                 "World Chess Championship 2026 against Javokhir Sindarov (Uzbekistan, winner of the Candidates "
                 "Tournament 2026), had not been played as of this date. Magnus Carlsen gave the title up in 2023 and "
                 "did not play the 2023 match (Ding Liren beat Ian Nepomniachtchi then)."),
    "women": ("Women's world champion: Ju Wenjun (China) — she retained the title in 2025 against Tan Zhongyi; "
              "champion since 2018, five times."),
    "rating": ("Top of the FIDE classical rating list: Magnus Carlsen (Norway) — number one since 2011, "
               "rated about 2830; he is not the world champion (he gave the title up in 2023)."),
    "candidates": ("Candidates Tournament 2026 (Pegeia, Cyprus, 28 March – 16 April 2026): won by Javokhir Sindarov "
                   "(Uzbekistan), the challenger for the World Chess Championship 2026 against Gukesh Dommaraju. The "
                   "previous one, 2024 (Toronto), was won by Gukesh, who then took the title."),
}

_cache: dict[tuple[str, str], tuple[float, Optional[str]]] = {}
_cache_lock = threading.Lock()


def asks_current_facts(text: str) -> bool:
    """The words ask about the present state of the chess world."""
    return bool(_ASKS.search((text or "").replace("ё", "е")))


def topic_for(text: str) -> str:
    t = (text or "").replace("ё", "е")
    if _WOMEN.search(t):
        return "women"
    if _CANDIDATES.search(t):
        return "candidates"
    if _RATING.search(t):
        return "rating"
    return "champion"


def _clean(extract: str) -> str:
    lines = []
    for line in (extract or "").splitlines():
        s = line.strip()
        if not s or s.startswith("%") or "{{{" in s or s.startswith("[["):
            continue
        lines.append(s)
    return " ".join(lines)


def fetch_intro(lang: str, title: str) -> Optional[str]:
    """The introduction of a Wikipedia article (plain text), cached; None when unreachable."""
    key = (lang, title)
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_S:
            return hit[1]
    text = None
    try:
        resp = httpx.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={"action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1, "redirects": 1,
                    "format": "json", "titles": title},
            timeout=TIMEOUT_S,
            headers={"User-Agent": "HermesChessCoach/1.0 (chesster.io)"},
        )
        resp.raise_for_status()
        pages = (resp.json().get("query") or {}).get("pages") or {}
        page = next(iter(pages.values()), {}) if pages else {}
        text = _clean(page.get("extract") or "")[:MAX_CHARS] or None
    except Exception as exc:  # noqa: BLE001 — the fallback facts then go in
        logger.info("wikipedia unreachable for %s/%s: %s", lang, title, exc)
        text = None
    with _cache_lock:
        if text is not None or key not in _cache:
            _cache[key] = (now if text is not None else now - CACHE_TTL_S + 60, text)  # a miss is retried in a minute
    return text


def current_facts(question: str, fetch=None) -> Optional[dict]:
    """{"topic", "sources": [{lang, title, url, text}], "fetched_at", "fallback"} for a question about the
    present — or None when the question is about something else."""
    if not asks_current_facts(question):
        return None
    fetch = fetch or fetch_intro
    topic = topic_for(question)
    pages = list(PAGES[topic])
    if topic in EVENT:
        # The newest year page of the event (this year, else last year, else the one before): what happened
        # last, or what is coming — the general page does not say.
        year = datetime.now(timezone.utc).year
        for y in (year, year - 1, year - 2):
            title = f"{EVENT[topic]} {y}"
            if fetch("en", title):
                pages.insert(1, ("en", title))
                break
    sources = []
    for lang, title in pages:
        text = fetch(lang, title)
        if text:
            sources.append({"lang": lang, "title": title,
                            "url": f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
                            "text": text})
    fallback = not any(s["lang"] == "en" for s in sources)
    if fallback:
        sources.insert(0, {"lang": "en", "title": f"known facts as of {FALLBACK_AS_OF}", "url": "", "text": FALLBACK[topic]})
    return {"topic": topic, "sources": sources, "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "fallback": fallback}


def web_model(model: str, message: str) -> str:
    """*model* with OpenRouter's web-search suffix when the message asks about the present and the mode is
    on (config.COACH_WEB_ONLINE): the model reads live web results this turn, beside the Wikipedia block."""
    from src import config

    suffix = config.COACH_WEB_ONLINE_SUFFIX or ""
    if not config.COACH_WEB_ONLINE or not suffix or not model or model.endswith(suffix):
        return model
    return f"{model}{suffix}" if asks_current_facts(message) else model


def facts_text(facts: dict) -> str:
    return "\n".join(f"- {s['title']}" + (f" ({s['url']})" if s.get("url") else "") + f": {s['text']}" for s in facts["sources"])


def facts_block(facts: Optional[dict]) -> str:
    """The turn-context block for the text coach; "" when there is nothing."""
    if not facts:
        return ""
    if facts["fallback"]:
        head = (f"## Current facts of the chess world — Wikipedia was unreachable, these are facts known for certain "
                f"as of {FALLBACK_AS_OF}")
        tail = (f"Answer from these and SAY the date («по данным на {FALLBACK_AS_OF}»); if the question is about something "
                "later (a match or a tournament after that date), say you cannot check it right now.")
    else:
        head = f"## Verified current facts (Wikipedia, fetched today {facts['fetched_at']})"
        tail = (f"Answer the question about the current state from this block, in your own words, and say it is "
                f"Wikipedia's data as of today ({facts['fetched_at']}).")
    return (
        f"{head}\n{facts_text(facts)}\n{tail} You have no live internet of your own: never say you googled or "
        "checked anything beyond this block and your tools, and never state a newer fact from memory — your "
        "training data ends earlier than this."
    )


def facts_note(facts: Optional[dict]) -> Optional[str]:
    """The same for the voice coach, as one note (the site sends it to the model)."""
    if not facts:
        return None
    return "[Facts] " + facts_block(facts).replace("\n", " ")


# ── the tool (the voice coach's site calls it on a `fact` intent; the model may call it too) ────────────

CURRENT_FACTS_SCHEMA = {
    "name": "current_facts",
    "description": (
        "The current state of the chess world, fetched now from Wikipedia (not from memory): the world champion "
        "(men's, women's), the top of the FIDE rating list, the last Candidates Tournament and title match. Call it "
        "for any question about who is champion / number one / what happened lately, and answer from its text, "
        "saying the date. You have no live internet otherwise — never claim you googled."
    ),
    "parameters": {
        "type": "object",
        "properties": {"question": {"type": "string", "description": "The student's question, as said."}},
        "required": ["question"],
    },
}


def _handle_current_facts(args: dict, **kwargs) -> str:
    import json

    question = str(args.get("question") or kwargs.get("student_message") or kwargs.get("utterance") or "")
    facts = current_facts(question) if question else None
    if facts is None:
        # The model asked for facts on its own words: default to the champion page.
        facts = current_facts("кто сейчас чемпион мира по шахматам")
    return json.dumps({**facts, "note": facts_note(facts)}, ensure_ascii=False)


try:
    from tools.registry import registry

    registry.register(
        name="current_facts",
        toolset="chess",
        schema=CURRENT_FACTS_SCHEMA,
        handler=_handle_current_facts,
        description="The current state of the chess world, fetched now (champion, ratings, last events).",
        emoji="📰",
    )
except Exception:  # noqa: BLE001 — outside the agent framework (tests of the module alone)
    logger.debug("current_facts tool not registered", exc_info=True)
