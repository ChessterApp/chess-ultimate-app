"""Unit tests for Tool 1: search_web."""

from unittest.mock import MagicMock, patch

import pytest

from src.tools.web_search import search_web


@pytest.mark.unit
def test_returns_results():
    """search_web returns a list of result dicts on valid query."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "Heading": "Chess",
        "AbstractText": "Chess is a board game.",
        "AbstractURL": "https://en.wikipedia.org/wiki/Chess",
        "RelatedTopics": [
            {"Text": "Chess opening - first moves", "FirstURL": "https://example.com/openings"},
        ],
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("src.tools.web_search.httpx.get", return_value=mock_resp):
        results = search_web("chess openings")

    assert len(results) >= 1
    assert results[0]["title"] == "Chess"
    assert results[0]["snippet"] == "Chess is a board game."


@pytest.mark.unit
def test_empty_query():
    """Empty query returns empty list without making HTTP call."""
    results = search_web("")
    assert results == []

    results = search_web("   ")
    assert results == []


@pytest.mark.unit
def test_result_schema():
    """Each result has title, url, and snippet keys."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "Heading": "Test",
        "AbstractText": "Test snippet",
        "AbstractURL": "https://example.com",
        "RelatedTopics": [],
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("src.tools.web_search.httpx.get", return_value=mock_resp):
        results = search_web("test")

    for r in results:
        assert "title" in r
        assert "url" in r
        assert "snippet" in r
        assert isinstance(r["title"], str)
        assert isinstance(r["url"], str)
        assert isinstance(r["snippet"], str)


@pytest.mark.unit
def test_timeout_handling():
    """Timeout returns empty list, not an exception."""
    import httpx as httpx_lib

    with patch("src.tools.web_search.httpx.get", side_effect=httpx_lib.TimeoutException("timed out")):
        results = search_web("test query")

    assert results == []
