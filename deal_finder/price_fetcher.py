"""
Price fetcher — wraps shoppingcomparisoncli (shoppingagent) for current prices.

Imports shoppingagent.aggregator directly (no subprocess).
Expects shoppingagent to be installed as editable package or available at SHOPPING_CLI_PATH.
"""
import sys
import os
from pathlib import Path
from dataclasses import dataclass


def _ensure_shopping_cli_on_path():
    path = os.getenv("SHOPPING_CLI_PATH", "../shoppingagent")
    resolved = Path(path).resolve()
    if str(resolved) not in sys.path and resolved.exists():
        sys.path.insert(0, str(resolved))


_ensure_shopping_cli_on_path()


@dataclass
class PriceResult:
    retailer: str
    price: float
    currency: str
    condition: str
    availability: str
    url: str


async def fetch_current_prices(item_name: str) -> list[PriceResult]:
    """
    Fetch current prices for item_name across Best Buy, eBay, Walmart, Google Shopping.
    Returns empty list on any failure — deal agent handles missing data gracefully.
    """
    try:
        from aggregator import run_all  # type: ignore
        from resolver import resolve    # type: ignore
        from connectors.bestbuy import BestBuyConnector
        from connectors.ebay import EbayConnector
        from connectors.google_shopping import GoogleShoppingConnector
        from connectors.walmart import WalmartConnector

        product = await resolve(item_name, upc=None)
        connectors = [
            BestBuyConnector(),
            EbayConnector(),
            GoogleShoppingConnector(),
            WalmartConnector(),
        ]
        results = await run_all(product, connectors)
        return [
            PriceResult(
                retailer=r.store,
                price=r.price,
                currency=r.currency,
                condition=r.condition,
                availability=r.availability,
                url=r.url,
            )
            for r in results
        ]
    except Exception:
        return []
