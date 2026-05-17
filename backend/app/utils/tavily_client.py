"""Thin wrapper around the Tavily Search REST API."""

from __future__ import annotations

import requests

from .logger import get_logger

logger = get_logger("glas.tavily")

_TAVILY_URL = "https://api.tavily.com/search"


class TavilyClient:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Search Tavily. Returns list of {title, url, content} dicts; empty list on error."""
        try:
            resp = requests.post(
                _TAVILY_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "advanced",
                    "include_raw_content": False,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                }
                for r in data.get("results", [])
            ]
        except Exception as exc:
            logger.warning("Tavily search failed for query %r: %s", query, exc)
            return []
