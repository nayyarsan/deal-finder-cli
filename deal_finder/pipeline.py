"""
Daily deal-finder pipeline.

Runs each active watchlist item through:
  1. Keepa — Amazon price history (items with ASIN only)
  2. price_fetcher — current prices across all configured retailers
  3. deal_agent — produces a buy/hold/monitor verdict

Results are written to data/alerts.json for consumption by jarvis.
"""
import asyncio
import json
import logging
from pathlib import Path

from deal_finder.watchlist import WatchlistDB
from deal_finder.keepa import get_amazon_history, get_current_amazon_price
from deal_finder.price_fetcher import fetch_current_prices
from deal_finder.deal_agent import analyze

log = logging.getLogger(__name__)

ALERTS_PATH = Path("data/alerts.json")


async def _process_item(db: WatchlistDB, item) -> dict | None:
    """Fetch prices for a single watchlist item and return a verdict dict."""
    log.info("Processing item %d: %s", item.id, item.name)
    prices = []

    # --- Keepa (Amazon history) ------------------------------------------
    if item.asin:
        try:
            history = await get_amazon_history(item.asin)
            for entry in history:
                db.log_price(
                    watchlist_id=item.id,
                    retailer="amazon",
                    price=entry["price"],
                    source="keepa",
                )

            current_price = await get_current_amazon_price(item.asin)
            if current_price is not None:
                db.log_price(
                    watchlist_id=item.id,
                    retailer="amazon",
                    price=current_price,
                    source="keepa",
                )
                prices.append({"retailer": "amazon", "price": current_price})
        except ValueError as exc:
            # KEEPA_API_KEY not set — log clearly and skip
            log.warning("Keepa skipped for %s: %s", item.name, exc)
        except Exception as exc:  # noqa: BLE001
            log.warning("Keepa error for %s (%s): %s", item.name, item.asin, exc)

    # --- Multi-retailer current prices ------------------------------------
    try:
        results = await fetch_current_prices(item.name)
        for r in results:
            db.log_price(
                watchlist_id=item.id,
                retailer=r.retailer,
                price=r.price,
                source="shoppingcli",
            )
            prices.append({"retailer": r.retailer, "price": r.price})
    except Exception as exc:  # noqa: BLE001
        log.warning("price_fetcher error for %s: %s", item.name, exc)

    if not prices:
        return None

    history_records = db.get_price_history(item.id, days=90)
    verdict = analyze(item, prices, history_records)
    return {"item": item.name, "verdict": verdict}


async def run_pipeline() -> None:
    """Entry-point for the daily GitHub Actions run."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db = WatchlistDB()
    items = db.list_items(active_only=True)
    log.info("Found %d active watchlist items", len(items))

    alerts = []
    for item in items:
        result = await _process_item(db, item)
        if result:
            alerts.append(result)

    ALERTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALERTS_PATH.write_text(json.dumps(alerts, indent=2))
    log.info("Wrote %d alerts to %s", len(alerts), ALERTS_PATH)


if __name__ == "__main__":
    asyncio.run(run_pipeline())
