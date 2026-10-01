"""Performance signals: Hacker News lookups and first-party analytics CSV import.

Signal keys carry their provenance (``hn_points``) or are the canonical English metric names
(``views``, ``clicks``) so benchmarks never mix public proxies with first-party numbers silently.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from ..models import ContentItem, canonical_url, item_id_for_url
from ..net import Fetcher
from ..store import Store
from .extract import guess_lang, shorten, to_iso

HN_SEARCH = "https://hn.algolia.com/api/v1/search"
HN_RECHECK_DAYS = 14
_BOM = chr(0xFEFF)
_NBSP = chr(0xA0)

_ALIASES: dict[str, tuple[str, ...]] = {
    "url": ("url", "link", "odkaz"),
    "title": ("title", "headline", "nadpis", "nazev"),
    "text": ("text", "caption", "popis"),
    "impressions": ("impressions", "zobrazeni", "reach", "dosah"),
    "views": ("views", "videni", "shlednuti", "zhlednuti", "prehrani"),
    "clicks": ("clicks", "kliknuti"),
    "likes": ("likes", "reactions", "lajky", "reakce"),
    "shares": ("shares", "sdileni"),
    "comments": ("comments", "komentare"),
    "saves": ("saves", "ulozeni"),
    "watch_time": ("watch_time", "watchtime"),
    "ctr": ("ctr",),
    "published_at": ("published_at", "date", "datum"),
}
_ALIAS_LOOKUP = {alias: canonical for canonical, names in _ALIASES.items() for alias in names}
_SIGNAL_KEYS = ("impressions", "views", "clicks", "likes", "shares", "comments", "saves", "watch_time", "ctr")


def _page_key(url: str) -> str:
    """Canonical URL without the scheme, so http and https listings of one page compare equal."""
    return re.sub(r"^https?://", "", canonical_url(url))


# -- Hacker News ----------------------------------------------------------------------
def parse_hn_response(payload: dict, url: str) -> dict[str, float]:
    """``hn_points`` and ``hn_comments`` of the best matching story, or ``{}`` when none matches."""
    hits = payload.get("hits") if isinstance(payload, dict) else None
    wanted = _page_key(url)
    best: dict[str, Any] | None = None
    best_points = -1.0
    for hit in hits if isinstance(hits, list) else []:
        if not isinstance(hit, dict) or not isinstance(hit.get("url"), str) or _page_key(hit["url"]) != wanted:
            continue
        points = float(hit.get("points") or 0)
        if points > best_points:
            best, best_points = hit, points
    if best is None:
        return {}
    return {"hn_points": best_points, "hn_comments": float(best.get("num_comments") or 0)}


def _hn_lookup(fetcher: Fetcher, url: str) -> dict[str, float] | None:
    """Signals for a URL, ``{}`` when Hacker News has no such story, None when the API did not answer properly."""
    api = f"{HN_SEARCH}?query={quote(url, safe='')}&restrictSearchableAttributes=url&tags=story&hitsPerPage=5"
    resp = fetcher.get(api)
    if not resp.ok:
        return None
    try:
        return parse_hn_response(resp.json(), url)
    except ValueError:
        return None


def hn_signal(fetcher: Fetcher, url: str) -> dict[str, float]:
    """Look a URL up on Hacker News through the Algolia search API. ``{}`` when not found or on HTTP errors."""
    return _hn_lookup(fetcher, url) or {}


def enrich_signals(
    store: Store,
    fetcher: Fetcher,
    *,
    limit: int = 100,
    sources: tuple[str, ...] = ("hn",),
    now: Callable[[], datetime] | None = None,
) -> int:
    """Add ``hn_*`` signals to stored real items with a URL. Returns the number of items updated.

    At most ``limit`` items are looked up per call, newest first. Items looked up without a match carry
    ``meta["hn_checked"]`` and are not asked again for two weeks, so repeated calls make progress.
    """
    if "hn" not in sources:
        return 0
    clock = now or (lambda: datetime.now(timezone.utc))
    stamp = clock()
    asked = updated = 0
    for item in store.iter_items(synthetic=False):
        if asked >= limit:
            break
        if not item.url or "hn_points" in item.signals:
            continue
        previous = item.meta.get("hn_checked")
        if previous:
            try:
                if (stamp - datetime.fromisoformat(previous)).days < HN_RECHECK_DAYS:
                    continue
            except (TypeError, ValueError):
                pass
        asked += 1
        try:
            found = _hn_lookup(fetcher, item.url)
        except Exception:  # network trouble
            found = None
        if found is None:  # no proper answer: leave the item untouched and retry next time
            continue
        item.meta["hn_checked"] = stamp.isoformat(timespec="seconds")
        if found:
            item.signals.update(found)
            updated += 1
        store.upsert_item(item)
    return updated


# -- first-party analytics CSV --------------------------------------------------------
def _header_key(header: str) -> str:
    text = unicodedata.normalize("NFKD", header.strip().lstrip(_BOM))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _read_text(source: str | Path) -> str:
    if isinstance(source, str) and ("\n" in source or "\r" in source):
        return source.lstrip(_BOM)
    raw = Path(source).read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1250", errors="replace")


def _detect_delimiter(text: str) -> str:
    first = next((line for line in text.splitlines() if line.strip()), "")
    counts = {d: first.count(d) for d in (",", ";", "\t")}
    best = max(counts, key=lambda d: (counts[d], d == ","))
    return best if counts[best] else ","


def _to_number(raw: str, decimal_comma: bool) -> float | None:
    text = raw.strip().replace(_NBSP, "").replace(" ", "").rstrip("%")
    if not text or not re.fullmatch(r"[+-]?[\d.,]*\d[\d.,]*", text):
        return None
    if "," in text and "." in text:
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        text = text.replace(thousands, "").replace(decimal, ".")
    elif "," in text:
        grouped = re.fullmatch(r"[+-]?\d{1,3}(,\d{3})+", text) is not None
        text = text.replace(",", "") if grouped and not decimal_comma else text.replace(",", ".")
    elif re.fullmatch(r"[+-]?\d{1,3}(\.\d{3}){2,}", text):
        text = text.replace(".", "")
    try:
        return float(text)
    except ValueError:
        return None


def _parse_date(raw: str) -> str | None:
    text = raw.strip()
    if not text:
        return None
    iso = to_iso(text)
    if iso:
        return iso
    match = re.fullmatch(r"(\d{1,2})[./-]\s*(\d{1,2})[./-]\s*(\d{4})(?:[ T]+(\d{1,2}):(\d{2}))?", text)
    if not match:
        return None
    first, second, year, hour, minute = match.groups()
    day, month = int(first), int(second)
    if month > 12 >= day:  # unambiguous month-first date such as 03/25/2026
        day, month = month, day
    return to_iso(f"{int(year):04d}-{month:02d}-{day:02d}T{int(hour or 0):02d}:{minute or '00'}:00")


def import_analytics_csv(
    store: Store, source: str | Path, brand_id: str, *, platform: str = "blog", format: str = "post"
) -> int:
    """Import first-party analytics rows as items (``meta.first_party`` is True). Returns rows imported.

    ``source`` is a file path or the CSV text itself (detected by a newline). Delimiter (comma,
    semicolon, tab), BOM, decimal commas and English or Czech header names are detected.
    """
    text = _read_text(source)
    delimiter = _detect_delimiter(text)
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    if not rows:
        return 0
    columns: dict[str, int] = {}
    for index, header in enumerate(rows[0]):
        canonical = _ALIAS_LOOKUP.get(_header_key(header))
        if canonical:
            columns.setdefault(canonical, index)  # when two columns share a meaning the first one wins
    imported = 0
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def cell(row: list[str], name: str) -> str:
        index = columns.get(name)
        return row[index].strip() if index is not None and index < len(row) else ""

    for row in rows[1:]:
        title = cell(row, "title")
        if not title:
            continue
        url = cell(row, "url")
        body = cell(row, "text")
        signals = {}
        for key in _SIGNAL_KEYS:
            value = _to_number(cell(row, key), decimal_comma=delimiter != ",")
            if value is not None:
                signals[key] = value
        digest = hashlib.sha1((brand_id + title).encode("utf-8")).hexdigest()[:12]
        item_id = item_id_for_url(url) if url else f"fp-{digest}"
        store.upsert_item(ContentItem(
            id=item_id, brand_id=brand_id, platform=platform, format=format, title=shorten(title, 300),
            url=canonical_url(url) if url else None, excerpt=shorten(body, 300), lang=guess_lang(f"{title} {body}"),
            published_at=_parse_date(cell(row, "published_at")), signals=signals,
            meta={"first_party": True, "source": "analytics_csv"}, fetched_at=stamp,
        ))
        imported += 1
    return imported
