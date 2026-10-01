"""SQLite persistence for brands, content items, cached analysis and crawl state.

One JSON blob per row keeps the schema stable while models evolve; the columns that queries
filter on are duplicated next to it.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .models import Brand, ContentItem

SCHEMA = """
CREATE TABLE IF NOT EXISTS brands (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, cohort TEXT NOT NULL, synthetic INTEGER NOT NULL DEFAULT 0,
    json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY, brand_id TEXT NOT NULL, platform TEXT NOT NULL, format TEXT NOT NULL,
    lang TEXT NOT NULL, synthetic INTEGER NOT NULL DEFAULT 0, published_at TEXT, json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_brand ON items(brand_id);
CREATE INDEX IF NOT EXISTS idx_items_platform ON items(platform);
CREATE TABLE IF NOT EXISTS analysis (item_id TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS fetch_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, url TEXT NOT NULL,
    status INTEGER, bytes INTEGER, note TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


class Store:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        if self.path != ":memory:":
            self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- brands ---------------------------------------------------------------------
    def upsert_brand(self, brand: Brand) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO brands(id, name, cohort, synthetic, json) VALUES (?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, cohort=excluded.cohort, "
                "synthetic=excluded.synthetic, json=excluded.json",
                (brand.id, brand.name, brand.cohort, int(brand.synthetic), _dump(brand.to_dict())),
            )

    def get_brand(self, brand_id: str) -> Brand | None:
        with self._lock:
            row = self._db.execute("SELECT json FROM brands WHERE id=?", (brand_id,)).fetchone()
        return Brand.from_dict(json.loads(row["json"])) if row else None

    def list_brands(self, cohort: str | None = None, synthetic: bool | None = None) -> list[Brand]:
        sql, args = "SELECT json FROM brands WHERE 1=1", []
        if cohort:
            sql += " AND cohort=?"
            args.append(cohort)
        if synthetic is not None:
            sql += " AND synthetic=?"
            args.append(int(synthetic))
        with self._lock:
            rows = self._db.execute(sql + " ORDER BY id", args).fetchall()
        return [Brand.from_dict(json.loads(r["json"])) for r in rows]

    # -- items ----------------------------------------------------------------------
    def upsert_item(self, item: ContentItem) -> bool:
        """Insert or update. Returns True when the item is new."""
        with self._lock, self._db:
            exists = self._db.execute("SELECT 1 FROM items WHERE id=?", (item.id,)).fetchone()
            self._db.execute(
                "INSERT INTO items(id, brand_id, platform, format, lang, synthetic, published_at, json) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET brand_id=excluded.brand_id, "
                "platform=excluded.platform, format=excluded.format, lang=excluded.lang, "
                "synthetic=excluded.synthetic, published_at=excluded.published_at, json=excluded.json",
                (item.id, item.brand_id, item.platform, item.format, item.lang, int(item.synthetic),
                 item.published_at, _dump(item.to_dict())),
            )
        return exists is None

    def get_item(self, item_id: str) -> ContentItem | None:
        with self._lock:
            row = self._db.execute("SELECT json FROM items WHERE id=?", (item_id,)).fetchone()
        return ContentItem.from_dict(json.loads(row["json"])) if row else None

    def _item_query(self, select: str, filters: dict[str, Any]) -> tuple[str, list[Any]]:
        sql = f"{select} FROM items i JOIN brands b ON b.id = i.brand_id WHERE 1=1"
        args: list[Any] = []
        for column, key in (("i.brand_id", "brand_id"), ("b.cohort", "cohort"), ("i.platform", "platform"),
                            ("i.format", "format"), ("i.lang", "lang")):
            if filters.get(key):
                sql += f" AND {column}=?"
                args.append(filters[key])
        if filters.get("synthetic") is not None:
            sql += " AND i.synthetic=?"
            args.append(int(filters["synthetic"]))
        return sql, args

    def iter_items(self, *, limit: int | None = None, **filters: Any) -> Iterator[ContentItem]:
        """Filters: brand_id, cohort, platform, format, lang, synthetic."""
        sql, args = self._item_query("SELECT i.json AS json", filters)
        sql += " ORDER BY i.published_at DESC, i.id"
        if limit:
            sql += " LIMIT ?"
            args.append(limit)
        with self._lock:
            rows = self._db.execute(sql, args).fetchall()
        for row in rows:
            yield ContentItem.from_dict(json.loads(row["json"]))

    def count_items(self, **filters: Any) -> int:
        sql, args = self._item_query("SELECT COUNT(*) AS n", filters)
        with self._lock:
            return int(self._db.execute(sql, args).fetchone()["n"])

    def cohort_of(self, brand_id: str) -> str | None:
        brand = self.get_brand(brand_id)
        return brand.cohort if brand else None

    # -- analysis cache -------------------------------------------------------------
    def set_analysis(self, item_id: str, data: dict[str, Any]) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO analysis(item_id, json) VALUES (?,?) "
                "ON CONFLICT(item_id) DO UPDATE SET json=excluded.json",
                (item_id, _dump(data)),
            )

    def get_analysis(self, item_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT json FROM analysis WHERE item_id=?", (item_id,)).fetchone()
        return json.loads(row["json"]) if row else None

    # -- key/value state ------------------------------------------------------------
    def kv_get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def kv_set(self, key: str, value: Any) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO kv(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, _dump(value)),
            )

    # -- crawl log ------------------------------------------------------------------
    def log_fetch(self, url: str, status: int | None, size: int | None = None, note: str = "") -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO fetch_log(ts, url, status, bytes, note) VALUES (?,?,?,?,?)",
                (_now(), url, status, size, note),
            )

    def recent_fetches(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT ts, url, status, bytes, note FROM fetch_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # -- overview -------------------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        with self._lock:
            by_cohort = self._db.execute(
                "SELECT b.cohort AS k, COUNT(*) AS n FROM items i JOIN brands b ON b.id=i.brand_id GROUP BY b.cohort"
            ).fetchall()
            by_platform = self._db.execute("SELECT platform AS k, COUNT(*) AS n FROM items GROUP BY platform").fetchall()
            brands = self._db.execute("SELECT COUNT(*) AS n FROM brands").fetchone()["n"]
            items = self._db.execute("SELECT COUNT(*) AS n FROM items").fetchone()["n"]
            synthetic = self._db.execute("SELECT COUNT(*) AS n FROM items WHERE synthetic=1").fetchone()["n"]
        return {
            "brands": brands,
            "items": items,
            "synthetic_items": synthetic,
            "by_cohort": {r["k"]: r["n"] for r in by_cohort},
            "by_platform": {r["k"]: r["n"] for r in by_platform},
        }
