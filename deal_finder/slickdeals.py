"""
Slickdeals RSS feed checker.

Searches the Slickdeals frontpage/search RSS feed for deals matching a query.
Returns a list of deal dicts — gracefully returns [] on any network or parse error.
"""
from __future__ import annotations

import logging

import feedparser

log = logging.getLogger(__name__)

SLICKDEALS_RSS_URL = (
    "https://slickdeals.net/newsearch.php"
    "?mode=frontpage&searcharea=deals&q={query}&rss=1"
)


def check_slickdeals(query: str = "") -> list[dict]:
    """
    Search the Slickdeals RSS feed for deals matching *query*.

    Returns a list of dicts, each with keys: title, url, summary.
    Returns an empty list on any failure (network error, parse error, etc.).
    """
    try:
        url = SLICKDEALS_RSS_URL.format(query=query.replace(" ", "+"))
        feed = feedparser.parse(url)
        return [
            {
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "summary": entry.get("summary", ""),
            }
            for entry in feed.entries
        ]
    except Exception as exc:  # noqa: BLE001
        log.warning("Slickdeals RSS error for %r: %s", query, exc)
        return []
