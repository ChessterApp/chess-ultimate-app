"""Tool 1: search_web — Web search via DuckDuckGo instant answers."""

import logging

import httpx

from tools.registry import registry

logger = logging.getLogger(__name__)

SEARCH_SCHEMA = {
    "type": "function",
    "function": {
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
    },
}

TIMEOUT = 10


def search_web(query: str) -> list[dict]:
    """Execute a web search and return results."""
    if not query or not query.strip():
        return []

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
        return []
    except Exception:
        logger.exception("Web search failed for query: %s", query)
        return []

    results = []

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
