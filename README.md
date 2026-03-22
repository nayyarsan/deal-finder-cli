# deal-finder-cli

Deal intelligence engine used by [jarvis-personal-agent](https://github.com/nayyarsan/jarvis-personal-agent) via WhatsApp.

## What it does

- Maintains a personal shopping watchlist (SQLite)
- Fetches current prices via [shoppingcomparisoncli](https://github.com/nayyarsan/shoppingcomparisoncli) (Best Buy, eBay, Walmart, Google Shopping)
- Tracks Amazon price history via Keepa API
- Monitors Slickdeals RSS for watchlist matches
- Runs a deal intelligence agent daily — produces verdicts: `buy_now`, `hold`, `move_store`, `cutthroat`, `monitor`
- Writes `data/alerts.json` to the `output` branch for jarvis to consume
- GitHub Actions runs the full pipeline daily at 08:00 PT

## Structure

```
deal_finder/
  watchlist.py        — SQLite CRUD: add/remove/list watchlist items + price history
  price_fetcher.py    — Wraps shoppingcomparisoncli for current prices
  keepa.py            — Amazon ASIN price history via Keepa API
  slickdeals.py       — RSS monitor with fuzzy + LLM match confirmation
  deal_calendar.yaml  — Category → sale event mapping
  deal_agent.py       — Verdict logic: buy_now / hold / move_store / cutthroat / monitor
  alerts.py           — Writes alerts.json output for jarvis
  cli.py              — Typer CLI entry point
data/
  watchlist.db        — SQLite (gitignored)
  alerts.json         — Written by pipeline, committed to output branch
.github/
  workflows/
    shopping_tracker.yml      — Daily GitHub Actions pipeline
    reverse-engineering-docs.md — gh-aw: auto-generates docs on push to main
```

## Usage with jarvis

jarvis `ShoppingModule` calls `deal_finder --item "query"` for on-demand lookups.
jarvis `WatchlistModule` calls `deal_finder --watchlist add|remove|list|check`.

## Setup

```bash
pip install -e .
cp .env.example .env
# Add API keys: KEEPA_API_KEY, BESTBUY_API_KEY, EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, SERPAPI_KEY
```
