"""Crossref REST API client (https://api.crossref.org), the authority used to verify DOIs.

Etiquette: a ``mailto`` goes into the User-Agent header so requests land in the polite pool.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlencode

from ..config import DEFAULT_USER_AGENT
from ..net import Fetcher, Response
from .grading import classify_design
from .models import (
    ResearchApiError, Study, clean_text, format_author_parts, make_study_id, normalize_doi,
)

SELECT_FIELDS = (
    "DOI,title,subtitle,author,issued,published-print,published-online,container-title,"
    "is-referenced-by-count,abstract,type,relation,update-to,updated-by"
)
_YEAR_KEYS = ("issued", "published-print", "published-online", "published")
_HINT_TYPES = frozenset({"posted-content", "book", "monograph", "edited-book", "reference-book"})
_RETRACTED_TITLE = re.compile(r"^\s*(?:\[?retracted\]?\s*[:\-]|retraction(?:\s+(?:note|notice))?\s*[:\-])", re.I)
_JATS_TITLE = re.compile(r"<jats:title>.*?</jats:title>", re.I | re.S)
_LEADING_ABSTRACT = re.compile(r"^abstract\s*[:.]\s*", re.I)


def _year_of(message: dict[str, Any], key: str) -> int | None:
    parts = (message.get(key) or {}).get("date-parts")
    if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
        first = parts[0][0]
        return first if isinstance(first, int) else None
    return None


def years_in(message: dict[str, Any]) -> frozenset[int]:
    """Every publication year Crossref knows (online-first and issue year can differ)."""
    return frozenset(y for y in (_year_of(message, k) for k in _YEAR_KEYS) if y is not None)


def _first(values: Any) -> str:
    if isinstance(values, list) and values:
        return clean_text(values[0] if isinstance(values[0], str) else "")
    return clean_text(values) if isinstance(values, str) else ""


def _full_title(message: dict[str, Any]) -> str:
    title = _first(message.get("title"))
    subtitle = _first(message.get("subtitle"))
    if title and subtitle and subtitle.lower() not in title.lower():
        return f"{title}: {subtitle}"
    return title


def is_retracted(message: dict[str, Any], title: str = "") -> bool:
    """Retraction or withdrawal declared through update records, relations or the title."""
    for key in ("update-to", "updated-by"):
        for entry in message.get(key) or []:
            if isinstance(entry, dict):
                kind = f"{entry.get('type', '')} {entry.get('label', '')}".lower()
                if "retract" in kind or "withdraw" in kind:
                    return True
    relation = message.get("relation") or {}
    if isinstance(relation, dict) and any("retract" in str(k).lower() for k in relation):
        return True
    return bool(_RETRACTED_TITLE.match(title))


def _abstract(message: dict[str, Any]) -> str | None:
    raw = message.get("abstract")
    if not isinstance(raw, str):
        return None
    text = _LEADING_ABSTRACT.sub("", clean_text(_JATS_TITLE.sub(" ", raw)))
    return text or None


def parse_message(message: dict[str, Any]) -> tuple[Study, frozenset[int]] | None:
    """Convert a Crossref work ``message`` into ``(Study, all known years)``; None if unusable."""
    doi = normalize_doi(message.get("DOI"))
    title = _full_title(message)
    if not doi or not title:
        return None
    authors: list[str] = []
    for person in message.get("author") or []:
        if not isinstance(person, dict):
            continue
        name = (
            format_author_parts(person.get("given"), person.get("family"))
            if person.get("family") else clean_text(person.get("name")) or None
        )
        if name:
            authors.append(name)
    venue = _first(message.get("container-title")) or None
    work_type = str(message.get("type") or "").lower()
    years = years_in(message)
    year = next((y for y in (_year_of(message, k) for k in _YEAR_KEYS) if y is not None), None)
    abstract = _abstract(message)
    cited = message.get("is-referenced-by-count")
    peer_reviewed: bool | None = None
    if work_type in ("journal-article", "proceedings-article"):
        peer_reviewed = True
    elif work_type == "posted-content":
        peer_reviewed = False
    study = Study(
        id=make_study_id(doi=doi),
        title=title,
        authors=authors,
        year=year,
        venue=venue,
        doi=doi,
        url=f"https://doi.org/{doi}",
        abstract=abstract,
        cited_by=cited if isinstance(cited, int) else None,
        design=classify_design(title, abstract, venue, work_type=work_type if work_type in _HINT_TYPES else None),
        source="crossref",
        retracted=is_retracted(message, title),
        peer_reviewed=peer_reviewed,
    )
    return study, years


class CrossrefClient:
    def __init__(self, fetcher: Fetcher, mailto: str | None = None, base_url: str = "https://api.crossref.org"):
        self.fetcher = fetcher
        self.mailto = mailto
        self.base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.mailto:
            headers["User-Agent"] = f"{DEFAULT_USER_AGENT} (mailto:{self.mailto})"
        return headers

    def _get(self, url: str) -> Response:
        return self.fetcher.get(url, headers=self._headers())

    @staticmethod
    def _message(resp: Response, url: str) -> dict[str, Any]:
        if not resp.ok:
            raise ResearchApiError(f"crossref: HTTP {resp.status} for {url}")
        try:
            data = resp.json()
        except ValueError as err:
            raise ResearchApiError(f"crossref: response is not JSON ({err})") from err
        message = data.get("message") if isinstance(data, dict) else None
        if not isinstance(message, dict):
            raise ResearchApiError("crossref: response has no message object")
        return message

    def lookup(self, doi: str) -> tuple[Study, frozenset[int]] | None:
        """Fetch one work by DOI with every publication year Crossref lists; None if unknown."""
        clean = normalize_doi(doi)
        if not clean:
            return None
        url = f"{self.base_url}/works/{quote(clean, safe='/')}"
        resp = self._get(url)
        if resp.status == 404:
            return None
        return parse_message(self._message(resp, url))

    def by_doi(self, doi: str) -> Study | None:
        found = self.lookup(doi)
        return found[0] if found else None

    def search_detailed(self, query: str, *, rows: int = 10) -> list[tuple[Study, frozenset[int]]]:
        params = {"query.bibliographic": query, "rows": max(1, min(rows, 100))}
        url = f"{self.base_url}/works?{urlencode({**params, 'select': SELECT_FIELDS}, quote_via=quote, safe=',:')}"
        resp = self._get(url)
        if resp.status == 400:       # an API version that rejects a select key: ask for the full record
            url = f"{self.base_url}/works?{urlencode(params, quote_via=quote)}"
            resp = self._get(url)
        items = self._message(resp, url).get("items")
        if not isinstance(items, list):
            raise ResearchApiError("crossref: response has no items list")
        parsed = (parse_message(item) for item in items if isinstance(item, dict))
        return [p for p in parsed if p is not None]

    def search(self, query: str, *, rows: int = 10) -> list[Study]:
        return [study for study, _ in self.search_detailed(query, rows=rows)]
