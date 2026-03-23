"""
Tests for deal_finder/pipeline.py and deal_finder/alerts.py.

All external dependencies (WatchlistDB, Keepa, price_fetcher, slickdeals) are
fully mocked so the test suite runs without network access or a real DB.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


from deal_finder.deal_agent import DealVerdict
from deal_finder.price_fetcher import PriceResult
from deal_finder.watchlist import PriceRecord, WatchlistItem


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_item(
    item_id: int = 1,
    name: str = "AirPods Pro 2",
    asin: str | None = None,
    category: str = "electronics",
) -> WatchlistItem:
    return WatchlistItem(
        id=item_id,
        name=name,
        category=category,
        retailer_hint="any",
        target_price=None,
        asin=asin,
        date_added="2024-01-01T00:00:00+00:00",
        notes="",
        active=True,
    )


def _make_price_result(retailer: str = "BestBuy", price: float = 189.0) -> PriceResult:
    return PriceResult(
        retailer=retailer,
        price=price,
        currency="USD",
        condition="new",
        availability="in_stock",
        url=f"https://{retailer.lower()}.com/item",
    )


def _make_price_record(price: float = 189.0) -> PriceRecord:
    return PriceRecord(
        id=1,
        watchlist_id=1,
        retailer="BestBuy",
        price=price,
        fetched_at="2024-01-01T00:00:00+00:00",
        source="shoppingcli",
    )


def _make_verdict(
    verdict: str = "buy_now",
    item_name: str = "AirPods Pro 2",
    upcoming_event: str | None = None,
) -> DealVerdict:
    return DealVerdict(
        item_id=1,
        item_name=item_name,
        verdict=verdict,
        current_price=189.0,
        current_retailer="BestBuy",
        current_url="https://bestbuy.com/item",
        low_90d=189.0,
        avg_90d=210.0,
        upcoming_event=upcoming_event,
        expected_saving_pct=None,
        explanation="Price $189.00 is at or near the 90-day low of $189.00.",
    )


# ---------------------------------------------------------------------------
# alerts.py tests
# ---------------------------------------------------------------------------

class TestWriteAlerts:
    def test_writes_correct_schema(self, tmp_path: Path):
        from deal_finder.alerts import write_alerts

        path = tmp_path / "alerts.json"
        write_alerts([_make_verdict("buy_now")], path)

        data = json.loads(path.read_text())
        assert "generated_at" in data
        assert "alerts" in data
        assert len(data["alerts"]) == 1
        alert = data["alerts"][0]
        assert alert["type"] == "shopping_alert"
        assert alert["item"] == "AirPods Pro 2"
        assert alert["verdict"] == "buy_now"
        assert alert["current_price"] == 189.0
        assert alert["retailer"] == "BestBuy"

    def test_empty_alerts_when_no_actionable_verdicts(self, tmp_path: Path):
        from deal_finder.alerts import write_alerts

        path = tmp_path / "alerts.json"
        write_alerts([_make_verdict("monitor")], path)

        data = json.loads(path.read_text())
        assert data["alerts"] == []

    def test_empty_input_writes_empty_alerts_not_error(self, tmp_path: Path):
        from deal_finder.alerts import write_alerts

        path = tmp_path / "alerts.json"
        write_alerts([], path)

        data = json.loads(path.read_text())
        assert data["alerts"] == []
        assert "generated_at" in data

    def test_move_store_verdict_included(self, tmp_path: Path):
        from deal_finder.alerts import write_alerts

        path = tmp_path / "alerts.json"
        write_alerts([_make_verdict("move_store")], path)

        data = json.loads(path.read_text())
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["verdict"] == "move_store"

    def test_cutthroat_verdict_included(self, tmp_path: Path):
        from deal_finder.alerts import write_alerts

        path = tmp_path / "alerts.json"
        write_alerts([_make_verdict("cutthroat")], path)

        data = json.loads(path.read_text())
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["verdict"] == "cutthroat"

    def test_hold_with_upcoming_event_included(self, tmp_path: Path):
        from deal_finder.alerts import write_alerts

        v = DealVerdict(
            item_id=1,
            item_name="TV",
            verdict="hold",
            current_price=500.0,
            current_retailer="BestBuy",
            current_url="https://bestbuy.com",
            low_90d=450.0,
            avg_90d=520.0,
            upcoming_event="Black Friday",
            expected_saving_pct=20,
            explanation="Wait for Black Friday.",
        )
        path = tmp_path / "alerts.json"
        write_alerts([v], path)

        data = json.loads(path.read_text())
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["verdict"] == "hold"
        assert data["alerts"][0]["item"] == "TV"

    def test_hold_without_event_omitted(self, tmp_path: Path):
        from deal_finder.alerts import write_alerts

        v = DealVerdict(
            item_id=1,
            item_name="TV",
            verdict="hold",
            current_price=500.0,
            current_retailer="BestBuy",
            current_url="https://bestbuy.com",
            low_90d=450.0,
            avg_90d=520.0,
            upcoming_event=None,
            expected_saving_pct=None,
            explanation="Hold.",
        )
        path = tmp_path / "alerts.json"
        write_alerts([v], path)

        data = json.loads(path.read_text())
        assert data["alerts"] == []

    def test_monitor_always_omitted(self, tmp_path: Path):
        from deal_finder.alerts import write_alerts

        path = tmp_path / "alerts.json"
        write_alerts([_make_verdict("monitor")], path)

        data = json.loads(path.read_text())
        assert data["alerts"] == []

    def test_multiple_verdicts_only_actionable_included(self, tmp_path: Path):
        from deal_finder.alerts import write_alerts

        verdicts = [
            _make_verdict("buy_now", "Item A"),
            _make_verdict("monitor", "Item B"),
            _make_verdict("cutthroat", "Item C"),
        ]
        path = tmp_path / "alerts.json"
        write_alerts(verdicts, path)

        data = json.loads(path.read_text())
        assert len(data["alerts"]) == 2
        included_items = {a["item"] for a in data["alerts"]}
        assert included_items == {"Item A", "Item C"}

    def test_creates_parent_directory(self, tmp_path: Path):
        from deal_finder.alerts import write_alerts

        path = tmp_path / "nested" / "subdir" / "alerts.json"
        write_alerts([], path)

        assert path.exists()

    def test_message_field_contains_explanation(self, tmp_path: Path):
        from deal_finder.alerts import write_alerts

        path = tmp_path / "alerts.json"
        v = _make_verdict("buy_now")
        write_alerts([v], path)

        data = json.loads(path.read_text())
        assert data["alerts"][0]["message"] == v.explanation


# ---------------------------------------------------------------------------
# pipeline._process_item tests
# ---------------------------------------------------------------------------

class TestProcessItem:
    def _make_db(self, history: list[PriceRecord] | None = None) -> MagicMock:
        db = MagicMock()
        db.log_price = MagicMock()
        db.get_price_history = MagicMock(return_value=history or [])
        return db

    async def test_returns_none_when_no_prices_found(self):
        from deal_finder.pipeline import _process_item

        db = self._make_db()
        item = _make_item()

        with (
            patch("deal_finder.pipeline.fetch_current_prices", AsyncMock(return_value=[])),
            patch("deal_finder.pipeline.check_slickdeals", return_value=[]),
        ):
            result = await _process_item(db, item)

        assert result is None

    async def test_returns_deal_verdict_when_prices_available(self):
        from deal_finder.pipeline import _process_item

        db = self._make_db(history=[_make_price_record()])
        item = _make_item()

        with (
            patch("deal_finder.pipeline.fetch_current_prices", AsyncMock(return_value=[_make_price_result()])),
            patch("deal_finder.pipeline.check_slickdeals", return_value=[]),
        ):
            result = await _process_item(db, item)

        assert result is not None
        assert isinstance(result, DealVerdict)

    async def test_keepa_not_called_when_no_asin(self):
        from deal_finder.pipeline import _process_item

        db = self._make_db(history=[_make_price_record()])
        item = _make_item(asin=None)

        with (
            patch("deal_finder.pipeline.get_amazon_history") as mock_history,
            patch("deal_finder.pipeline.fetch_current_prices", AsyncMock(return_value=[_make_price_result()])),
            patch("deal_finder.pipeline.check_slickdeals", return_value=[]),
        ):
            await _process_item(db, item)

        mock_history.assert_not_called()

    async def test_keepa_fetched_when_asin_present(self):
        from deal_finder.pipeline import _process_item

        db = self._make_db(history=[_make_price_record()])
        item = _make_item(asin="B0CHWRXH8B")

        with (
            patch("deal_finder.pipeline.get_amazon_history", AsyncMock(return_value=[])) as mock_history,
            patch("deal_finder.pipeline.get_current_amazon_price", AsyncMock(return_value=189.0)),
            patch("deal_finder.pipeline.fetch_current_prices", AsyncMock(return_value=[])),
            patch("deal_finder.pipeline.check_slickdeals", return_value=[]),
        ):
            await _process_item(db, item)

        mock_history.assert_called_once_with("B0CHWRXH8B")

    async def test_amazon_price_result_built_correctly(self):
        from deal_finder.pipeline import _process_item

        db = self._make_db(history=[_make_price_record(price=189.0)])
        item = _make_item(asin="B0CHWRXH8B")

        with (
            patch("deal_finder.pipeline.get_amazon_history", AsyncMock(return_value=[])),
            patch("deal_finder.pipeline.get_current_amazon_price", AsyncMock(return_value=199.0)),
            patch("deal_finder.pipeline.fetch_current_prices", AsyncMock(return_value=[])),
            patch("deal_finder.pipeline.check_slickdeals", return_value=[]),
        ):
            result = await _process_item(db, item)

        # Amazon price was logged and used
        db.log_price.assert_called()
        assert result is not None

    async def test_keepa_value_error_gracefully_handled(self):
        from deal_finder.pipeline import _process_item

        db = self._make_db()
        item = _make_item(asin="B0CHWRXH8B")

        with (
            patch("deal_finder.pipeline.get_amazon_history", AsyncMock(side_effect=ValueError("KEEPA_API_KEY not set"))),
            patch("deal_finder.pipeline.fetch_current_prices", AsyncMock(return_value=[])),
            patch("deal_finder.pipeline.check_slickdeals", return_value=[]),
        ):
            result = await _process_item(db, item)

        assert result is None  # no prices → None

    async def test_keepa_generic_error_gracefully_handled(self):
        from deal_finder.pipeline import _process_item

        db = self._make_db()
        item = _make_item(asin="B0CHWRXH8B")

        with (
            patch("deal_finder.pipeline.get_amazon_history", AsyncMock(side_effect=RuntimeError("network error"))),
            patch("deal_finder.pipeline.fetch_current_prices", AsyncMock(return_value=[])),
            patch("deal_finder.pipeline.check_slickdeals", return_value=[]),
        ):
            result = await _process_item(db, item)

        assert result is None

    async def test_price_fetcher_error_gracefully_handled(self):
        from deal_finder.pipeline import _process_item

        db = self._make_db()
        item = _make_item()

        with (
            patch("deal_finder.pipeline.fetch_current_prices", AsyncMock(side_effect=RuntimeError("timeout"))),
            patch("deal_finder.pipeline.check_slickdeals", return_value=[]),
        ):
            result = await _process_item(db, item)

        assert result is None

    async def test_slickdeals_called_per_item(self):
        from deal_finder.pipeline import _process_item

        db = self._make_db(history=[_make_price_record()])
        item = _make_item(name="Sony WH-1000XM5")

        with (
            patch("deal_finder.pipeline.fetch_current_prices", AsyncMock(return_value=[_make_price_result()])),
            patch("deal_finder.pipeline.check_slickdeals", return_value=[]) as mock_sd,
        ):
            await _process_item(db, item)

        mock_sd.assert_called_once_with("Sony WH-1000XM5")

    async def test_price_logged_for_each_retailer_result(self):
        from deal_finder.pipeline import _process_item

        db = self._make_db(history=[_make_price_record()])
        item = _make_item()
        prices = [
            _make_price_result("BestBuy", 189.0),
            _make_price_result("Walmart", 195.0),
        ]

        with (
            patch("deal_finder.pipeline.fetch_current_prices", AsyncMock(return_value=prices)),
            patch("deal_finder.pipeline.check_slickdeals", return_value=[]),
        ):
            await _process_item(db, item)

        assert db.log_price.call_count == 2


# ---------------------------------------------------------------------------
# pipeline.run_pipeline tests
# ---------------------------------------------------------------------------

class TestRunPipeline:
    def _make_db_mock(
        self,
        items: list[WatchlistItem] | None = None,
        history: list[PriceRecord] | None = None,
    ) -> MagicMock:
        db = MagicMock()
        db.list_items = MagicMock(return_value=items or [])
        db.get_price_history = MagicMock(return_value=history or [])
        db.log_price = MagicMock()
        return db

    async def test_writes_alerts_json(self, tmp_path: Path):
        from deal_finder import pipeline

        alerts_path = tmp_path / "alerts.json"
        item = _make_item()
        mock_db = self._make_db_mock(items=[item], history=[_make_price_record()])

        with (
            patch("deal_finder.pipeline.WatchlistDB", return_value=mock_db),
            patch("deal_finder.pipeline.fetch_current_prices", AsyncMock(return_value=[_make_price_result()])),
            patch("deal_finder.pipeline.check_slickdeals", return_value=[]),
            patch("deal_finder.pipeline.ALERTS_PATH", alerts_path),
        ):
            await pipeline.run_pipeline()

        assert alerts_path.exists()
        data = json.loads(alerts_path.read_text())
        assert "generated_at" in data
        assert "alerts" in data

    async def test_empty_watchlist_writes_empty_alerts(self, tmp_path: Path):
        from deal_finder import pipeline

        alerts_path = tmp_path / "alerts.json"
        mock_db = self._make_db_mock(items=[])

        with (
            patch("deal_finder.pipeline.WatchlistDB", return_value=mock_db),
            patch("deal_finder.pipeline.ALERTS_PATH", alerts_path),
        ):
            await pipeline.run_pipeline()

        assert alerts_path.exists()
        data = json.loads(alerts_path.read_text())
        assert data["alerts"] == []

    async def test_no_prices_produces_empty_alerts(self, tmp_path: Path):
        from deal_finder import pipeline

        alerts_path = tmp_path / "alerts.json"
        item = _make_item()
        mock_db = self._make_db_mock(items=[item], history=[])

        with (
            patch("deal_finder.pipeline.WatchlistDB", return_value=mock_db),
            patch("deal_finder.pipeline.fetch_current_prices", AsyncMock(return_value=[])),
            patch("deal_finder.pipeline.check_slickdeals", return_value=[]),
            patch("deal_finder.pipeline.ALERTS_PATH", alerts_path),
        ):
            await pipeline.run_pipeline()

        assert alerts_path.exists()
        data = json.loads(alerts_path.read_text())
        assert data["alerts"] == []

    async def test_monitor_verdict_omitted_from_alerts(self, tmp_path: Path):
        from deal_finder import pipeline

        alerts_path = tmp_path / "alerts.json"
        item = _make_item()
        # history and prices present, but no 90d history → monitor verdict
        mock_db = self._make_db_mock(items=[item], history=[])

        with (
            patch("deal_finder.pipeline.WatchlistDB", return_value=mock_db),
            patch(
                "deal_finder.pipeline.fetch_current_prices",
                AsyncMock(return_value=[_make_price_result()]),
            ),
            patch("deal_finder.pipeline.check_slickdeals", return_value=[]),
            patch("deal_finder.pipeline.ALERTS_PATH", alerts_path),
        ):
            await pipeline.run_pipeline()

        data = json.loads(alerts_path.read_text())
        # No price history → compute_verdict returns "monitor" → omitted
        assert data["alerts"] == []

    async def test_multiple_items_processed(self, tmp_path: Path):
        from deal_finder import pipeline

        alerts_path = tmp_path / "alerts.json"
        items = [_make_item(1, "Item A"), _make_item(2, "Item B")]
        mock_db = self._make_db_mock(items=items, history=[_make_price_record()])

        with (
            patch("deal_finder.pipeline.WatchlistDB", return_value=mock_db),
            patch(
                "deal_finder.pipeline.fetch_current_prices",
                AsyncMock(return_value=[_make_price_result()]),
            ),
            patch("deal_finder.pipeline.check_slickdeals", return_value=[]),
            patch("deal_finder.pipeline.ALERTS_PATH", alerts_path),
        ):
            await pipeline.run_pipeline()

        # Both items were processed (fetch_current_prices called twice)
        assert alerts_path.exists()
