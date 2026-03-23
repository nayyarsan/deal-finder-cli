"""
Alerts writer — produces data/alerts.json for consumption by jarvis-personal-agent.

Schema
------
{
    "generated_at": "<ISO timestamp>",
    "alerts": [
        {
            "type": "shopping_alert",
            "item": "<item name>",
            "verdict": "<verdict>",
            "message": "<explanation>",
            "current_price": <float | null>,
            "retailer": "<retailer | null>",
            "url": "<url | null>"
        }
    ]
}

Included verdicts
-----------------
  buy_now, move_store, cutthroat — always included (immediately actionable).
  hold                           — included when an upcoming sale event is known
                                   (time-sensitive; buyer should act soon).
  monitor                        — always omitted (no action required).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from deal_finder.deal_agent import DealVerdict

ACTIONABLE_VERDICTS = {"buy_now", "move_store", "cutthroat"}
DEFAULT_PATH = Path("data/alerts.json")


def _is_actionable(verdict: DealVerdict) -> bool:
    """Return True if this verdict should appear in alerts.json."""
    if verdict.verdict in ACTIONABLE_VERDICTS:
        return True
    # Include hold only when an upcoming sale event is explicitly known.
    if verdict.verdict == "hold" and verdict.upcoming_event:
        return True
    return False


def write_alerts(verdicts: list[DealVerdict], path: Path = DEFAULT_PATH) -> int:
    """
    Filter *verdicts* to actionable ones and write alerts.json to *path*.

    Always writes the file — an empty alerts list is valid output (not an error).
    Creates parent directories as needed.

    Returns the number of alerts written.
    """
    alerts = [
        {
            "type": "shopping_alert",
            "item": v.item_name,
            "verdict": v.verdict,
            "message": v.explanation,
            "current_price": v.current_price,
            "retailer": v.current_retailer,
            "url": v.current_url,
        }
        for v in verdicts
        if _is_actionable(v)
    ]
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "alerts": alerts,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2))
    return len(alerts)
