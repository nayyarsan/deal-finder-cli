"""
Tests for deal_finder/slickdeals.py — RSS and Ollama calls are fully mocked.
"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deal_finder.slickdeals import (
    SlickdealMatch,
    _confirm_with_llm,
    _extract_price,
    _fetch_rss_deals,
    check_slickdeals,
)
from deal_finder.watchlist import WatchlistDB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path: Path) -> WatchlistDB:
    """Return an in-memory WatchlistDB backed by a temp file."""
    return WatchlistDB(db_path=tmp_path / "test.db")


def _mock_http_response(text: str = "", json_data: dict | None = None, status: int = 200):
    """Build a minimal mock httpx response."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = text
    mock_resp.json.return_value = json_data or {}
    return mock_resp


def _patch_async_client(mock_get=None, mock_post=None):
    """
    Return a context-manager patch for httpx.AsyncClient that wires up
    optional get/post AsyncMock callables.
    """
    mock_client = AsyncMock()
    if mock_get is not None:
        mock_client.get = mock_get
    if mock_post is not None:
        mock_client.post = mock_post

    mock_cls = MagicMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_cls


# ---------------------------------------------------------------------------
# Unit tests: _extract_price
# ---------------------------------------------------------------------------

class TestExtractPrice:
    def test_simple_price(self):
        assert _extract_price("Sony WH-1000XM5 $299.99") == pytest.approx(299.99)

    def test_price_with_commas(self):
        assert _extract_price("MacBook Pro $1,299.00") == pytest.approx(1299.00)

    def test_price_no_cents(self):
        assert _extract_price("AirPods Pro $249") == pytest.approx(249.0)

    def test_no_price_returns_none(self):
        assert _extract_price("Great deal on headphones") is None

    def test_first_price_returned_when_multiple(self):
        # When two prices appear, the first one wins
        assert _extract_price("Was $399.99, now $299.99") == pytest.approx(399.99)

    def test_empty_string_returns_none(self):
        assert _extract_price("") is None


# ---------------------------------------------------------------------------
# Unit tests: _fetch_rss_deals
# ---------------------------------------------------------------------------

class TestFetchRssDeals:
    def _rss_xml(self, entries: list[tuple[str, str]]) -> str:
        """Build a minimal RSS 2.0 document."""
        items = "".join(
            f"<item><title>{t}</title><link>{u}</link></item>"
            for t, u in entries
        )
        return (
            '<?xml version="1.0"?>'
            "<rss version=\"2.0\"><channel>"
            f"{items}"
            "</channel></rss>"
        )

    async def test_returns_list_of_dicts(self):
        xml = self._rss_xml([("Sony Headphones $199", "https://slickdeals.net/1")])
        mock_cls = _patch_async_client(
            mock_get=AsyncMock(return_value=_mock_http_response(text=xml))
        )
        with patch("deal_finder.slickdeals.httpx.AsyncClient", mock_cls):
            deals = await _fetch_rss_deals()

        assert len(deals) == 1
        assert deals[0]["title"] == "Sony Headphones $199"
        assert deals[0]["url"] == "https://slickdeals.net/1"

    async def test_multiple_entries_returned(self):
        xml = self._rss_xml([
            ("Deal A $10", "https://slickdeals.net/a"),
            ("Deal B $20", "https://slickdeals.net/b"),
        ])
        mock_cls = _patch_async_client(
            mock_get=AsyncMock(return_value=_mock_http_response(text=xml))
        )
        with patch("deal_finder.slickdeals.httpx.AsyncClient", mock_cls):
            deals = await _fetch_rss_deals()

        assert len(deals) == 2

    async def test_empty_feed_returns_empty_list(self):
        xml = self._rss_xml([])
        mock_cls = _patch_async_client(
            mock_get=AsyncMock(return_value=_mock_http_response(text=xml))
        )
        with patch("deal_finder.slickdeals.httpx.AsyncClient", mock_cls):
            deals = await _fetch_rss_deals()

        assert deals == []

    async def test_http_error_propagates(self):
        mock_resp = _mock_http_response()
        mock_resp.raise_for_status.side_effect = Exception("HTTP 503")
        mock_cls = _patch_async_client(mock_get=AsyncMock(return_value=mock_resp))
        with patch("deal_finder.slickdeals.httpx.AsyncClient", mock_cls):
            with pytest.raises(Exception, match="HTTP 503"):
                await _fetch_rss_deals()


# ---------------------------------------------------------------------------
# Unit tests: _confirm_with_llm
# ---------------------------------------------------------------------------

class TestConfirmWithLlm:
    async def test_yes_response_returns_true(self):
        mock_cls = _patch_async_client(
            mock_post=AsyncMock(
                return_value=_mock_http_response(json_data={"response": "YES"})
            )
        )
        with patch("deal_finder.slickdeals.httpx.AsyncClient", mock_cls):
            result = await _confirm_with_llm("Sony WH-1000XM5 $199", "Sony WH-1000XM5")

        assert result is True

    async def test_yes_with_trailing_text_returns_true(self):
        mock_cls = _patch_async_client(
            mock_post=AsyncMock(
                return_value=_mock_http_response(
                    json_data={"response": "YES, this is a match."}
                )
            )
        )
        with patch("deal_finder.slickdeals.httpx.AsyncClient", mock_cls):
            result = await _confirm_with_llm("Sony WH-1000XM5 $199", "Sony WH-1000XM5")

        assert result is True

    async def test_no_response_returns_false(self):
        mock_cls = _patch_async_client(
            mock_post=AsyncMock(
                return_value=_mock_http_response(json_data={"response": "NO"})
            )
        )
        with patch("deal_finder.slickdeals.httpx.AsyncClient", mock_cls):
            result = await _confirm_with_llm("Unrelated Deal", "Sony WH-1000XM5")

        assert result is False

    async def test_network_error_returns_false(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
        mock_cls = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("deal_finder.slickdeals.httpx.AsyncClient", mock_cls):
            result = await _confirm_with_llm("Some Deal", "Some Item")

        assert result is False

    async def test_uses_ollama_base_url_env(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://custom-host:9999")

        captured_urls: list[str] = []

        async def capturing_post(url, **_kwargs):
            captured_urls.append(url)
            return _mock_http_response(json_data={"response": "YES"})

        mock_cls = _patch_async_client(mock_post=capturing_post)
        with patch("deal_finder.slickdeals.httpx.AsyncClient", mock_cls):
            await _confirm_with_llm("deal", "item")

        assert captured_urls[0] == "http://custom-host:9999/api/generate"

    async def test_uses_ollama_model_env(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_MODEL", "llama3")

        captured_payloads: list[dict] = []

        async def capturing_post(_url, json=None, **_kwargs):
            captured_payloads.append(json or {})
            return _mock_http_response(json_data={"response": "YES"})

        mock_cls = _patch_async_client(mock_post=capturing_post)
        with patch("deal_finder.slickdeals.httpx.AsyncClient", mock_cls):
            await _confirm_with_llm("deal", "item")

        assert captured_payloads[0]["model"] == "llama3"


# ---------------------------------------------------------------------------
# Integration tests: check_slickdeals
# ---------------------------------------------------------------------------

class TestCheckSlickdeals:
    """
    Tests for the high-level check_slickdeals() function.

    _fetch_rss_deals and _confirm_with_llm are patched at module level so
    that only the orchestration logic is exercised here.
    """

    def _make_deals(self, entries: list[tuple[str, str]]) -> list[dict]:
        return [{"title": t, "url": u} for t, u in entries]

    async def test_returns_confirmed_matches(self, tmp_path):
        db = _make_db(tmp_path)
        db.add_item("Sony WH-1000XM5")

        deals = self._make_deals([("Sony WH-1000XM5 Headphones $249", "https://sd.net/1")])

        with (
            patch("deal_finder.slickdeals._fetch_rss_deals", AsyncMock(return_value=deals)),
            patch("deal_finder.slickdeals._confirm_with_llm", AsyncMock(return_value=True)),
        ):
            matches = await check_slickdeals(db)

        assert len(matches) == 1
        match = matches[0]
        assert isinstance(match, SlickdealMatch)
        assert match.deal_title == "Sony WH-1000XM5 Headphones $249"
        assert match.deal_url == "https://sd.net/1"
        assert match.llm_confirmed is True
        assert match.price == pytest.approx(249.0)
        assert match.fuzzy_score > 80

    async def test_llm_rejected_matches_excluded(self, tmp_path):
        db = _make_db(tmp_path)
        db.add_item("Sony WH-1000XM5")

        deals = self._make_deals([("Sony WH-1000XM5 Headphones $249", "https://sd.net/1")])

        with (
            patch("deal_finder.slickdeals._fetch_rss_deals", AsyncMock(return_value=deals)),
            patch("deal_finder.slickdeals._confirm_with_llm", AsyncMock(return_value=False)),
        ):
            matches = await check_slickdeals(db)

        assert matches == []

    async def test_low_fuzzy_score_excluded(self, tmp_path):
        db = _make_db(tmp_path)
        db.add_item("Sony WH-1000XM5")

        # Title shares no meaningful tokens with the watchlist item
        deals = self._make_deals([("Garden Hose 50ft $19.99", "https://sd.net/2")])

        with (
            patch("deal_finder.slickdeals._fetch_rss_deals", AsyncMock(return_value=deals)),
            patch(
                "deal_finder.slickdeals._confirm_with_llm", AsyncMock(return_value=True)
            ) as mock_llm,
        ):
            matches = await check_slickdeals(db)

        # LLM must not be called because fuzzy score is too low
        mock_llm.assert_not_called()
        assert matches == []

    async def test_empty_watchlist_returns_empty(self, tmp_path):
        db = _make_db(tmp_path)  # no items added

        with patch(
            "deal_finder.slickdeals._fetch_rss_deals", AsyncMock(return_value=[])
        ) as mock_fetch:
            matches = await check_slickdeals(db)

        mock_fetch.assert_not_called()
        assert matches == []

    async def test_rss_fetch_failure_returns_empty(self, tmp_path):
        db = _make_db(tmp_path)
        db.add_item("Sony WH-1000XM5")

        with patch(
            "deal_finder.slickdeals._fetch_rss_deals",
            AsyncMock(side_effect=Exception("Network error")),
        ):
            matches = await check_slickdeals(db)

        assert matches == []

    async def test_price_logged_when_present(self, tmp_path):
        db = _make_db(tmp_path)
        item_id = db.add_item("Sony WH-1000XM5")

        deals = self._make_deals([("Sony WH-1000XM5 $199.99", "https://sd.net/3")])

        with (
            patch("deal_finder.slickdeals._fetch_rss_deals", AsyncMock(return_value=deals)),
            patch("deal_finder.slickdeals._confirm_with_llm", AsyncMock(return_value=True)),
        ):
            await check_slickdeals(db)

        history = db.get_price_history(item_id)
        assert len(history) == 1
        assert history[0].price == pytest.approx(199.99)
        assert history[0].source == "slickdeals"
        assert history[0].retailer == "slickdeals"

    async def test_no_price_in_title_still_returns_match(self, tmp_path):
        db = _make_db(tmp_path)
        item_id = db.add_item("Sony WH-1000XM5")

        deals = self._make_deals([("Sony WH-1000XM5 Headphones on sale", "https://sd.net/4")])

        with (
            patch("deal_finder.slickdeals._fetch_rss_deals", AsyncMock(return_value=deals)),
            patch("deal_finder.slickdeals._confirm_with_llm", AsyncMock(return_value=True)),
        ):
            matches = await check_slickdeals(db)

        assert len(matches) == 1
        assert matches[0].price is None

        # No price row should be logged when price is absent
        history = db.get_price_history(item_id)
        assert history == []

    async def test_only_active_watchlist_items_matched(self, tmp_path):
        db = _make_db(tmp_path)
        item_id = db.add_item("Sony WH-1000XM5")
        db.remove_item(item_id)  # deactivate the item

        deals = self._make_deals([("Sony WH-1000XM5 Headphones $249", "https://sd.net/5")])

        with (
            patch("deal_finder.slickdeals._fetch_rss_deals", AsyncMock(return_value=deals)),
            patch(
                "deal_finder.slickdeals._confirm_with_llm", AsyncMock(return_value=True)
            ) as mock_llm,
        ):
            matches = await check_slickdeals(db)

        mock_llm.assert_not_called()
        assert matches == []

    async def test_watchlist_id_on_match(self, tmp_path):
        db = _make_db(tmp_path)
        item_id = db.add_item("Sony WH-1000XM5")

        deals = self._make_deals([("Sony WH-1000XM5 $199", "https://sd.net/6")])

        with (
            patch("deal_finder.slickdeals._fetch_rss_deals", AsyncMock(return_value=deals)),
            patch("deal_finder.slickdeals._confirm_with_llm", AsyncMock(return_value=True)),
        ):
            matches = await check_slickdeals(db)

        assert matches[0].watchlist_id == item_id
