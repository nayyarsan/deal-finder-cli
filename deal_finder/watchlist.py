"""
Watchlist SQLite store.

Tables:
  watchlist     — items the user wants to track
  price_history — price snapshots from all sources

Usage:
  from deal_finder.watchlist import WatchlistDB
  db = WatchlistDB()
  db.add_item("AirPods Pro 2", category="electronics")
"""
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


DB_PATH = Path("data/watchlist.db")


@dataclass
class WatchlistItem:
    id: int
    name: str
    category: str
    retailer_hint: str
    target_price: Optional[float]
    asin: Optional[str]
    date_added: str
    notes: str
    active: bool


@dataclass
class PriceRecord:
    id: int
    watchlist_id: int
    retailer: str
    price: float
    fetched_at: str
    source: str  # keepa | shoppingcli | slickdeals | flipp


class WatchlistDB:
    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._init()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _init(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    id            INTEGER PRIMARY KEY,
                    name          TEXT NOT NULL,
                    category      TEXT NOT NULL DEFAULT 'general',
                    retailer_hint TEXT NOT NULL DEFAULT 'any',
                    target_price  REAL,
                    asin          TEXT,
                    date_added    TEXT NOT NULL,
                    notes         TEXT NOT NULL DEFAULT '',
                    active        INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS price_history (
                    id           INTEGER PRIMARY KEY,
                    watchlist_id INTEGER NOT NULL REFERENCES watchlist(id),
                    retailer     TEXT NOT NULL,
                    price        REAL NOT NULL,
                    fetched_at   TEXT NOT NULL,
                    source       TEXT NOT NULL
                );
            """)

    def add_item(
        self,
        name: str,
        category: str = "general",
        retailer_hint: str = "any",
        target_price: Optional[float] = None,
        asin: Optional[str] = None,
        notes: str = "",
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO watchlist (name, category, retailer_hint, target_price, asin, date_added, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, category, retailer_hint, target_price, asin, now, notes),
            )
            return cur.lastrowid

    def remove_item(self, item_id: int):
        with self._conn() as conn:
            conn.execute("UPDATE watchlist SET active = 0 WHERE id = ?", (item_id,))

    def list_items(self, active_only: bool = True) -> list[WatchlistItem]:
        with self._conn() as conn:
            q = "SELECT id, name, category, retailer_hint, target_price, asin, date_added, notes, active FROM watchlist"
            if active_only:
                q += " WHERE active = 1"
            rows = conn.execute(q).fetchall()
        return [WatchlistItem(*r) for r in rows]

    def get_item(self, item_id: int) -> Optional[WatchlistItem]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, name, category, retailer_hint, target_price, asin, date_added, notes, active "
                "FROM watchlist WHERE id = ?", (item_id,)
            ).fetchone()
        return WatchlistItem(*row) if row else None

    def log_price(self, watchlist_id: int, retailer: str, price: float, source: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO price_history (watchlist_id, retailer, price, fetched_at, source) "
                "VALUES (?, ?, ?, ?, ?)",
                (watchlist_id, retailer, price, now, source),
            )

    def get_price_history(self, watchlist_id: int, days: int = 90) -> list[PriceRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, watchlist_id, retailer, price, fetched_at, source "
                "FROM price_history WHERE watchlist_id = ? "
                "AND fetched_at >= datetime('now', ?) "
                "ORDER BY fetched_at ASC",
                (watchlist_id, f"-{days} days"),
            ).fetchall()
        return [PriceRecord(*r) for r in rows]
