"""
Slickdeals RSS monitor — fuzzy-match deals against watchlist, confirm via LLM.

Fetches Slickdeals frontpage RSS feed, fuzzy-matches deal titles against
active watchlist items using rapidfuzz (threshold > 80), then confirms
matches via Ollama phi4-mini. Confirmed matches are logged to price_history
with source='slickdeals'.

Environment variables:
  OLLAMA_BASE_URL  — Ollama server base URL (default: http://localhost:11434)
  OLLAMA_MODEL     — model name to use for confirmation (default: phi4-mini)
"""
import logging
import os
import re
from dataclasses import dataclass

import feedparser
import httpx
from rapidfuzz import fuzz

from deal_finder.watchlist import WatchlistDB


log = logging.getLogger(__name__)

_RSS_FRONTPAGE = (
    "https://slickdeals.net/newsearch.php?mode=frontpage&searcharea=deals&rss=1"
)
_FUZZY_THRESHOLD = 80
_PRICE_RE = re.compile(r"\$[\d,]+\.?\d*")
_OLLAMA_DEFAULT_URL = "http://localhost:11434"


@dataclass
class SlickdealMatch:
    watchlist_id: int
    deal_title: str
    deal_url: str
    price: float | None
    fuzzy_score: float
    llm_confirmed: bool


def _extract_price(title: str) -> float | None:
    """Extract the first dollar amount from a deal title string."""
    match = _PRICE_RE.search(title)
    if not match:
        return None
    return float(match.group().replace("$", "").replace(",", ""))


async def _fetch_rss_deals() -> list[dict]:
    """Fetch and parse the Slickdeals frontpage RSS feed via httpx + feedparser."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(_RSS_FRONTPAGE)
        response.raise_for_status()
        content = response.text

    feed = feedparser.parse(content)
    return [
        {"title": entry.get("title", ""), "url": entry.get("link", "")}
        for entry in feed.entries
    ]


async def _confirm_with_llm(deal_title: str, watchlist_item: str) -> bool:
    """Ask Ollama whether this deal matches the watchlist item.

    Returns True only when the model replies with a response starting with YES.
    On any network or parse error the function returns False so that the
    caller can skip the match safely.
    """
    base_url = os.getenv("OLLAMA_BASE_URL", _OLLAMA_DEFAULT_URL).rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "phi4-mini")
    prompt = (
        f"Does this deal '{deal_title}' match the item '{watchlist_item}'? "
        "Reply YES or NO."
    )
    payload = {"model": model, "prompt": prompt, "stream": False}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{base_url}/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
        answer = data.get("response", "").strip().upper()
        return answer.startswith("YES")
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "Ollama confirmation failed for '%s' vs '%s': %s",
            deal_title,
            watchlist_item,
            exc,
        )
        return False


async def check_slickdeals(db: WatchlistDB) -> list[SlickdealMatch]:
    """Return confirmed matches for active watchlist items.

    Steps:
    1. Fetch Slickdeals frontpage RSS feed.
    2. For every deal × watchlist item pair, compute rapidfuzz token_set_ratio.
    3. Pairs scoring > 80 are sent to Ollama for a YES/NO confirmation.
    4. Confirmed matches are logged via WatchlistDB.log_price() and returned.
    """
    watchlist = db.list_items(active_only=True)
    if not watchlist:
        return []

    try:
        deals = await _fetch_rss_deals()
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to fetch Slickdeals RSS: %s", exc)
        return []

    confirmed: list[SlickdealMatch] = []

    for deal in deals:
        title = deal["title"]
        url = deal["url"]

        for item in watchlist:
            score = fuzz.token_set_ratio(title.lower(), item.name.lower())
            if score <= _FUZZY_THRESHOLD:
                continue

            llm_confirmed = await _confirm_with_llm(title, item.name)
            if not llm_confirmed:
                continue

            price = _extract_price(title)

            if price is not None:
                db.log_price(
                    watchlist_id=item.id,
                    retailer="slickdeals",
                    price=price,
                    source="slickdeals",
                )

            confirmed.append(
                SlickdealMatch(
                    watchlist_id=item.id,
                    deal_title=title,
                    deal_url=url,
                    price=price,
                    fuzzy_score=float(score),
                    llm_confirmed=True,
                )
            )

    return confirmed
