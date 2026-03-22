"""
Keepa integration — Amazon ASIN price history.

Fetches 90-day Amazon price history and current price from the Keepa API.
Requires KEEPA_API_KEY environment variable.

Keepa API docs: https://keepa.com/#!discuss/t/request-products/1
"""
import os
from datetime import datetime, timezone, timedelta

import httpx


_KEEPA_EPOCH = datetime(2011, 1, 1, tzinfo=timezone.utc)
_KEEPA_API_URL = "https://api.keepa.com/product"

# Keepa CSV index 0 = Amazon (new) prices; index 1 = third-party new prices
_AMAZON_CSV_INDEX = 0


def _keepa_minutes_to_datetime(keepa_minutes: int) -> datetime:
    """Convert Keepa epoch minutes to a UTC datetime."""
    return _KEEPA_EPOCH + timedelta(minutes=keepa_minutes)


def _get_api_key() -> str:
    """Return the Keepa API key or raise a clear error if unset."""
    key = os.getenv("KEEPA_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "KEEPA_API_KEY environment variable is not set. "
            "Set it to your Keepa API key before using Keepa integration."
        )
    return key


def _parse_csv_to_history(csv: list[int], cutoff: datetime) -> list[dict]:
    """
    Parse a Keepa CSV array into a list of {price, fetched_at} dicts.

    The CSV array is an interleaved sequence of [time, price, time, price, ...].
    - time  : Keepa minutes (minutes since 2011-01-01 UTC)
    - price : US cents; -1 means "not available"

    Only entries within the 90-day window (>= cutoff) are returned.
    """
    history: list[dict] = []
    for i in range(0, len(csv) - 1, 2):
        keepa_minutes = csv[i]
        raw_price = csv[i + 1]
        if raw_price == -1:
            continue
        ts = _keepa_minutes_to_datetime(keepa_minutes)
        if ts < cutoff:
            continue
        history.append(
            {
                "price": raw_price / 100.0,
                "fetched_at": ts.isoformat(),
            }
        )
    return history


async def get_amazon_history(asin: str) -> list[dict]:
    """Return list of {price, fetched_at} from Keepa for the last 90 days."""
    key = _get_api_key()
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)

    params = {
        "key": key,
        "domain": "1",  # amazon.com
        "asin": asin,
        "history": "1",
        "stats": "1",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(_KEEPA_API_URL, params=params)
        response.raise_for_status()
        data = response.json()

    products = data.get("products") or []
    if not products:
        return []

    product = products[0]
    csv_data = product.get("csv") or []
    if len(csv_data) <= _AMAZON_CSV_INDEX:
        return []

    amazon_csv = csv_data[_AMAZON_CSV_INDEX]
    if not amazon_csv:
        return []

    return _parse_csv_to_history(amazon_csv, cutoff)


async def get_current_amazon_price(asin: str) -> float | None:
    """Return the current Amazon price in USD, or None if unavailable."""
    key = _get_api_key()

    params = {
        "key": key,
        "domain": "1",
        "asin": asin,
        "history": "0",
        "stats": "1",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(_KEEPA_API_URL, params=params)
        response.raise_for_status()
        data = response.json()

    products = data.get("products") or []
    if not products:
        return None

    product = products[0]

    # stats.current contains the current prices indexed by CSV type
    stats = product.get("stats") or {}
    current = stats.get("current") or []
    if len(current) > _AMAZON_CSV_INDEX:
        raw = current[_AMAZON_CSV_INDEX]
        if raw is not None and raw != -1:
            return raw / 100.0

    return None
