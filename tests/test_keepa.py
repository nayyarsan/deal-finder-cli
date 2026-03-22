"""
Tests for deal_finder/keepa.py — all HTTP calls are mocked with httpx.
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from deal_finder.keepa import (
    _KEEPA_EPOCH,
    _keepa_minutes_to_datetime,
    _parse_csv_to_history,
    get_amazon_history,
    get_current_amazon_price,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_keepa_minutes(dt: datetime) -> int:
    """Convert a UTC datetime to Keepa minutes."""
    return int((dt - _KEEPA_EPOCH).total_seconds() / 60)


def _make_keepa_response(amazon_csv: list[int], current_price_cents: int | None = None) -> dict:
    """Build a minimal Keepa /product response."""
    stats: dict = {}
    if current_price_cents is not None:
        stats["current"] = [current_price_cents]  # index 0 = Amazon
    return {
        "products": [
            {
                "asin": "B09TEST1234",
                "csv": [amazon_csv],
                "stats": stats,
            }
        ]
    }


# ---------------------------------------------------------------------------
# Unit tests: helpers
# ---------------------------------------------------------------------------

class TestKeepaMinutesConversion:
    def test_epoch_zero(self):
        assert _keepa_minutes_to_datetime(0) == _KEEPA_EPOCH

    def test_one_day(self):
        expected = _KEEPA_EPOCH + timedelta(days=1)
        assert _keepa_minutes_to_datetime(24 * 60) == expected


class TestParseCsvToHistory:
    def _cutoff(self, days_ago: int = 90) -> datetime:
        return datetime.now(timezone.utc) - timedelta(days=days_ago)

    def test_empty_csv(self):
        assert _parse_csv_to_history([], self._cutoff()) == []

    def test_unavailable_prices_skipped(self):
        now_km = _to_keepa_minutes(datetime.now(timezone.utc) - timedelta(days=1))
        csv = [now_km, -1]
        assert _parse_csv_to_history(csv, self._cutoff()) == []

    def test_old_entries_excluded(self):
        old_km = _to_keepa_minutes(datetime.now(timezone.utc) - timedelta(days=100))
        csv = [old_km, 9999]  # 100 days ago, outside 90-day window
        assert _parse_csv_to_history(csv, self._cutoff()) == []

    def test_recent_entry_included(self):
        recent_km = _to_keepa_minutes(datetime.now(timezone.utc) - timedelta(days=1))
        csv = [recent_km, 9999]  # $99.99
        result = _parse_csv_to_history(csv, self._cutoff())
        assert len(result) == 1
        assert result[0]["price"] == pytest.approx(99.99)

    def test_price_conversion_cents_to_dollars(self):
        km = _to_keepa_minutes(datetime.now(timezone.utc) - timedelta(days=5))
        csv = [km, 24999]  # $249.99
        result = _parse_csv_to_history(csv, self._cutoff())
        assert result[0]["price"] == pytest.approx(249.99)

    def test_multiple_entries(self):
        km1 = _to_keepa_minutes(datetime.now(timezone.utc) - timedelta(days=30))
        km2 = _to_keepa_minutes(datetime.now(timezone.utc) - timedelta(days=10))
        csv = [km1, 10000, km2, 9500]
        result = _parse_csv_to_history(csv, self._cutoff())
        assert len(result) == 2
        assert result[0]["price"] == pytest.approx(100.00)
        assert result[1]["price"] == pytest.approx(95.00)

    def test_fetched_at_is_iso_string(self):
        km = _to_keepa_minutes(datetime.now(timezone.utc) - timedelta(days=1))
        result = _parse_csv_to_history([km, 5000], self._cutoff())
        datetime.fromisoformat(result[0]["fetched_at"])  # must not raise
        assert isinstance(datetime.fromisoformat(result[0]["fetched_at"]), datetime)


# ---------------------------------------------------------------------------
# Integration tests: get_amazon_history
# ---------------------------------------------------------------------------

class TestGetAmazonHistory:
    @pytest.fixture(autouse=True)
    def set_api_key(self, monkeypatch):
        monkeypatch.setenv("KEEPA_API_KEY", "test-key-123")

    def _mock_response(self, payload: dict):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = payload
        return mock_resp

    async def test_returns_history_list(self):
        km = _to_keepa_minutes(datetime.now(timezone.utc) - timedelta(days=5))
        payload = _make_keepa_response([km, 14999])

        with patch("deal_finder.keepa.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=self._mock_response(payload))

            result = await get_amazon_history("B09TEST1234")

        assert len(result) == 1
        assert result[0]["price"] == pytest.approx(149.99)
        assert "fetched_at" in result[0]

    async def test_empty_products_returns_empty(self):
        payload = {"products": []}

        with patch("deal_finder.keepa.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=self._mock_response(payload))

            result = await get_amazon_history("B09TEST1234")

        assert result == []

    async def test_no_csv_returns_empty(self):
        payload = {"products": [{"asin": "B09TEST1234", "csv": [], "stats": {}}]}

        with patch("deal_finder.keepa.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=self._mock_response(payload))

            result = await get_amazon_history("B09TEST1234")

        assert result == []

    async def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("KEEPA_API_KEY", raising=False)
        with pytest.raises(ValueError, match="KEEPA_API_KEY"):
            await get_amazon_history("B09TEST1234")

    async def test_filters_to_90_days(self):
        recent_km = _to_keepa_minutes(datetime.now(timezone.utc) - timedelta(days=10))
        old_km = _to_keepa_minutes(datetime.now(timezone.utc) - timedelta(days=95))
        payload = _make_keepa_response([old_km, 20000, recent_km, 19000])

        with patch("deal_finder.keepa.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=self._mock_response(payload))

            result = await get_amazon_history("B09TEST1234")

        assert len(result) == 1
        assert result[0]["price"] == pytest.approx(190.00)


# ---------------------------------------------------------------------------
# Integration tests: get_current_amazon_price
# ---------------------------------------------------------------------------

class TestGetCurrentAmazonPrice:
    @pytest.fixture(autouse=True)
    def set_api_key(self, monkeypatch):
        monkeypatch.setenv("KEEPA_API_KEY", "test-key-123")

    def _mock_response(self, payload: dict):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = payload
        return mock_resp

    async def test_returns_current_price(self):
        payload = _make_keepa_response([], current_price_cents=29999)

        with patch("deal_finder.keepa.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=self._mock_response(payload))

            price = await get_current_amazon_price("B09TEST1234")

        assert price == pytest.approx(299.99)

    async def test_unavailable_price_returns_none(self):
        payload = _make_keepa_response([], current_price_cents=-1)

        with patch("deal_finder.keepa.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=self._mock_response(payload))

            price = await get_current_amazon_price("B09TEST1234")

        assert price is None

    async def test_empty_products_returns_none(self):
        payload = {"products": []}

        with patch("deal_finder.keepa.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=self._mock_response(payload))

            price = await get_current_amazon_price("B09TEST1234")

        assert price is None

    async def test_no_stats_current_returns_none(self):
        payload = {"products": [{"asin": "B09TEST1234", "csv": [], "stats": {}}]}

        with patch("deal_finder.keepa.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=self._mock_response(payload))

            price = await get_current_amazon_price("B09TEST1234")

        assert price is None

    async def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("KEEPA_API_KEY", raising=False)
        with pytest.raises(ValueError, match="KEEPA_API_KEY"):
            await get_current_amazon_price("B09TEST1234")
