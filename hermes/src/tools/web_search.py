"""Tool 1: search_web — Web search via DuckDuckGo instant answers."""

import logging

import httpx

from tools.registry import registry

logger = logging.getLogger(__name__)

SEARCH_SCHEMA = {
    "name": "search_web",
    "description": "Search the web for chess-related information. Returns a list of results with title, URL, and snippet.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query string.",
            }
        },
        "required": ["query"],
    },
}

TIMEOUT = 10


def _wikipedia(query: str, lang: str, limit: int = 3) -> list[dict]:
    """Wikipedia's own search with each hit's introduction: the one web source that answers «who is the
    world champion now» (DuckDuckGo's instant answers have nothing on it — Alexander's screenshot, 20.10)."""
    try:
        resp = httpx.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={"action": "query", "generator": "search", "gsrsearch": query, "gsrlimit": limit,
                    "prop": "extracts", "exintro": 1, "explaintext": 1, "exlimit": limit, "format": "json"},
            timeout=TIMEOUT, headers={"User-Agent": "HermesChessCoach/1.0 (chesster.io)"},
        )
        resp.raise_for_status()
        pages = (resp.json().get("query") or {}).get("pages") or {}
    except Exception as exc:  # noqa: BLE001
        logger.info("wikipedia search failed (%s): %s", lang, exc)
        return []
    out = []
    for page in sorted(pages.values(), key=lambda p: p.get("index", 99)):
        text = " ".join(ln.strip() for ln in (page.get("extract") or "").splitlines()
                        if ln.strip() and not ln.strip().startswith("%") and "{{{" not in ln)
        if not text:
            continue
        title = page.get("title") or ""
        out.append({"title": title, "url": f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    "snippet": text[:700], "source": f"wikipedia-{lang}"})
    return out


def search_web(query: str) -> list[dict]:
    """Execute a web search and return results."""
    if not query or not query.strip():
        return []

    results = []
    cyrillic = any("\u0400" <= ch <= "\u04ff" for ch in query)
    for lang in (("ru", "en") if cyrillic else ("en", "ru")):
        results += _wikipedia(query, lang)
        if len(results) >= 3:
            break
    try:
        resp = httpx.get(
            "https://duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            timeout=TIMEOUT,
            headers={"User-Agent": "HermesChessCoach/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        logger.warning("Web search timed out for query: %s", query)
        return results
    except Exception:
        logger.exception("Web search failed for query: %s", query)
        return results

    # Abstract (top result)
    if data.get("AbstractText"):
        results.append({
            "title": data.get("Heading", ""),
            "url": data.get("AbstractURL", ""),
            "snippet": data["AbstractText"],
        })

    # Related topics
    for topic in data.get("RelatedTopics", []):
        if "Text" in topic:
            results.append({
                "title": topic.get("Text", "")[:80],
                "url": topic.get("FirstURL", ""),
                "snippet": topic.get("Text", ""),
            })
        # Sub-topics
        elif "Topics" in topic:
            for sub in topic["Topics"]:
                if "Text" in sub:
                    results.append({
                        "title": sub.get("Text", "")[:80],
                        "url": sub.get("FirstURL", ""),
                        "snippet": sub.get("Text", ""),
                    })

    return results


def _handle_search_web(args: dict, **kwargs) -> str:
    """Handler for the Hermes tool registry."""
    import json
    results = search_web(args.get("query", ""))
    return json.dumps(results, indent=2)


registry.register(
    name="search_web",
    toolset="chess",
    schema=SEARCH_SCHEMA,
    handler=_handle_search_web,
    description="Search the web for chess-related information.",
    emoji="🔍",
)
