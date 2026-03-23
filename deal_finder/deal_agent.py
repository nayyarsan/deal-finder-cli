"""
Deal intelligence agent.

For each active watchlist item, produces a verdict:
  buy_now    — at or near historical low, no better event coming soon
  hold       — better price expected at upcoming sale event
  move_store — significantly cheaper at a different retailer right now
  cutthroat  — below 90-day floor, act immediately
  monitor    — insufficient history or no strong signal yet

Verdict includes a one-sentence natural language explanation (via Ollama).
"""
from __future__ import annotations

import yaml
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from deal_finder.watchlist import WatchlistItem, PriceRecord
from deal_finder.price_fetcher import PriceResult

CALENDAR_PATH = Path(__file__).parent / "deal_calendar.yaml"
HOLD_WINDOW_DAYS = 60   # look ahead this many days for upcoming sale events
CUTTHROAT_THRESHOLD = 0.92  # below 92% of 90-day floor = cutthroat
MOVE_STORE_THRESHOLD = 0.85  # 15%+ cheaper elsewhere = move_store


@dataclass
class DealVerdict:
    item_id: int
    item_name: str
    verdict: str  # buy_now | hold | move_store | cutthroat | monitor
    current_price: Optional[float]
    current_retailer: Optional[str]
    current_url: Optional[str]
    low_90d: Optional[float]
    avg_90d: Optional[float]
    upcoming_event: Optional[str]
    expected_saving_pct: Optional[int]
    explanation: str


def _load_calendar() -> dict:
    if CALENDAR_PATH.exists():
        return yaml.safe_load(CALENDAR_PATH.read_text()) or {}
    return {}


def _upcoming_event(category: str, calendar: dict) -> Optional[tuple[str, int]]:
    """Return (event_name, discount_pct) if a sale event is within HOLD_WINDOW_DAYS."""
    today = datetime.now(timezone.utc)
    events = calendar.get(category, calendar.get("general", []))
    if not isinstance(events, list):
        return None
    for event in events:
        start = event.get("window_start", "")
        if not start:
            continue
        month, day = map(int, start.split("-"))
        candidate = today.replace(month=month, day=day)
        if candidate < today:
            candidate = candidate.replace(year=today.year + 1)
        delta = (candidate - today).days
        if 0 <= delta <= HOLD_WINDOW_DAYS:
            return event["event"], event.get("typical_discount_pct", 10)
    return None


def compute_verdict(
    item: WatchlistItem,
    current_prices: list[PriceResult],
    history: list[PriceRecord],
    calendar: Optional[dict] = None,
) -> DealVerdict:
    calendar = calendar or _load_calendar()
    best = min(current_prices, key=lambda p: p.price) if current_prices else None
    hist_prices = [r.price for r in history]

    low_90d = min(hist_prices) if hist_prices else None
    avg_90d = sum(hist_prices) / len(hist_prices) if hist_prices else None

    if best is None or low_90d is None:
        return DealVerdict(
            item_id=item.id, item_name=item.name, verdict="monitor",
            current_price=None, current_retailer=None, current_url=None,
            low_90d=low_90d, avg_90d=avg_90d,
            upcoming_event=None, expected_saving_pct=None,
            explanation="Not enough price data yet — monitoring.",
        )

    current = best.price

    # Cutthroat: below 90-day floor
    if current < low_90d * CUTTHROAT_THRESHOLD:
        return DealVerdict(
            item_id=item.id, item_name=item.name, verdict="cutthroat",
            current_price=current, current_retailer=best.retailer, current_url=best.url,
            low_90d=low_90d, avg_90d=avg_90d,
            upcoming_event=None, expected_saving_pct=None,
            explanation=f"Price ${current:.2f} is below the 90-day floor of ${low_90d:.2f} — act now.",
        )

    # Move store: best retailer is much cheaper than others
    if len(current_prices) > 1:
        sorted_prices = sorted(current_prices, key=lambda p: p.price)
        second_best = sorted_prices[1].price
        if current < second_best * MOVE_STORE_THRESHOLD:
            return DealVerdict(
                item_id=item.id, item_name=item.name, verdict="move_store",
                current_price=current, current_retailer=best.retailer, current_url=best.url,
                low_90d=low_90d, avg_90d=avg_90d,
                upcoming_event=None, expected_saving_pct=None,
                explanation=f"{best.retailer} is significantly cheaper at ${current:.2f} vs ${second_best:.2f} elsewhere.",
            )

    # Hold: upcoming sale event within window
    upcoming = _upcoming_event(item.category, calendar)
    if upcoming:
        event_name, discount_pct = upcoming
        expected_price = current * (1 - discount_pct / 100)
        saving = current - expected_price
        if saving > 5:  # only hold if saving is meaningful
            return DealVerdict(
                item_id=item.id, item_name=item.name, verdict="hold",
                current_price=current, current_retailer=best.retailer, current_url=best.url,
                low_90d=low_90d, avg_90d=avg_90d,
                upcoming_event=event_name, expected_saving_pct=discount_pct,
                explanation=f"Wait for {event_name} — expected ~{discount_pct}% off, saving ~${saving:.0f}.",
            )

    # Buy now: at or near historical low
    if current <= low_90d * 1.05:
        return DealVerdict(
            item_id=item.id, item_name=item.name, verdict="buy_now",
            current_price=current, current_retailer=best.retailer, current_url=best.url,
            low_90d=low_90d, avg_90d=avg_90d,
            upcoming_event=None, expected_saving_pct=None,
            explanation=f"Price ${current:.2f} is at or near the 90-day low of ${low_90d:.2f}.",
        )

    return DealVerdict(
        item_id=item.id, item_name=item.name, verdict="monitor",
        current_price=current, current_retailer=best.retailer, current_url=best.url,
        low_90d=low_90d, avg_90d=avg_90d,
        upcoming_event=None, expected_saving_pct=None,
        explanation=f"No strong signal yet. Current ${current:.2f}, 90d avg ${avg_90d:.2f}.",
    )
