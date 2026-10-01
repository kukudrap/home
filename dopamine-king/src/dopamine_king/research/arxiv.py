"""arXiv API client (Atom feed). Everything it returns is a preprint: not peer reviewed.

The arXiv terms ask for at most one request every three seconds; pair this client with an
``HttpFetcher`` configured accordingly.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import quote, urlencode

from ..net import Fetcher
from .models import ResearchApiError, Study, clean_text, format_author, normalize_doi

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"
_VERSION = re.compile(r"v\d+$")
_ID_PREFIX = re.compile(r"^(?:https?://(?:export\.)?arxiv\.org/(?:abs|pdf)/|arxiv:)", re.I)
_ID_SHAPE = re.compile(r"^(?:\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Za-z]{2})?/\d{7})$")


def normalize_arxiv_id(raw: str | None) -> str | None:
    """Bare arXiv id without prefix, ``.pdf`` and version suffix, or None if it is not an id."""
    if not raw or not isinstance(raw, str):
        return None
    value = _VERSION.sub("", re.sub(r"\.pdf$", "", _ID_PREFIX.sub("", raw.strip())))
    return value if _ID_SHAPE.match(value) else None


def _parse_entry(entry: ET.Element) -> Study | None:
    raw_id = entry.findtext(f"{ATOM}id") or ""
    if "/abs/" not in raw_id:             # the API reports errors as an entry titled "Error"
        return None
    arxiv_id = normalize_arxiv_id(raw_id.split("/abs/", 1)[1])
    title = clean_text(entry.findtext(f"{ATOM}title"))
    if not arxiv_id or not title:
        return None
    authors = [
        name for name in (format_author(a.findtext(f"{ATOM}name")) for a in entry.findall(f"{ATOM}author")) if name
    ]
    published = (entry.findtext(f"{ATOM}published") or "").strip()
    year = int(published[:4]) if published[:4].isdigit() else None
    return Study(
        id=f"arxiv:{arxiv_id}",
        title=title,
        authors=authors,
        year=year,
        venue="arXiv",
        doi=normalize_doi(entry.findtext(f"{ARXIV}doi")),
        url=f"https://arxiv.org/abs/{arxiv_id}",
        abstract=clean_text(entry.findtext(f"{ATOM}summary")) or None,
        cited_by=None,
        design="preprint",
        source="arxiv",
        peer_reviewed=False,
    )


def parse_feed(body: bytes | str) -> list[Study]:
    raw = body if isinstance(body, bytes) else body.encode("utf-8")
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise ResearchApiError("arxiv: refusing an XML document that declares a DTD")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as err:
        raise ResearchApiError(f"arxiv: invalid XML ({err})") from err
    parsed = (_parse_entry(e) for e in root.findall(f"{ATOM}entry"))
    return [s for s in parsed if s is not None]


class ArxivClient:
    def __init__(self, fetcher: Fetcher, base_url: str = "http://export.arxiv.org/api/query"):
        self.fetcher = fetcher
        self.base_url = base_url

    def _fetch(self, params: dict[str, object]) -> list[Study]:
        url = f"{self.base_url}?{urlencode(params, quote_via=quote, safe=':')}"
        resp = self.fetcher.get(url, headers={"Accept": "application/atom+xml"})
        if not resp.ok:
            raise ResearchApiError(f"arxiv: HTTP {resp.status} for {url}")
        return parse_feed(resp.body)

    def search(self, query: str, *, max_results: int = 10) -> list[Study]:
        tokens = re.findall(r"\w+", query)[:10]
        if not tokens:
            return []
        return self._fetch({
            "search_query": " AND ".join(f"all:{t}" for t in tokens),
            "start": 0,
            "max_results": max(1, min(max_results, 100)),
            "sortBy": "relevance",
            "sortOrder": "descending",
        })

    def by_id(self, arxiv_id: str) -> Study | None:
        clean = normalize_arxiv_id(arxiv_id)
        if not clean:
            return None
        found = self._fetch({"id_list": clean, "max_results": 1})
        return found[0] if found else None
