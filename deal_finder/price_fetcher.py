"""
Price fetcher — wraps shoppingcomparisoncli (shoppingagent) for current prices.

Imports shoppingagent.aggregator directly (no subprocess).
Expects shoppingcomparisoncli to be installed as a package dependency.
"""
from dataclasses import dataclass


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
