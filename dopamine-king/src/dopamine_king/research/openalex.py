"""OpenAlex works API client (https://docs.openalex.org).

All network access goes through the injected ``Fetcher``. Anything the API does not state stays
``None``; the design is only a keyword guess made by ``classify_design``.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode

from ..net import Fetcher
from .grading import classify_design
from .models import (
    ResearchApiError, Study, clean_text, format_author, make_study_id, normalize_doi,
)

# Root level fields only: the API cannot select nested fields.
SELECT_FIELDS = (
    "id,doi,title,display_name,publication_year,type,type_crossref,cited_by_count,"
    "is_retracted,abstract_inverted_index,authorships,primary_location"
)
_HINT_TYPES = frozenset({"preprint", "posted-content", "book", "monograph", "edited-book", "reference-book"})
_REVIEWED_TYPES = frozenset({"article", "review", "journal-article", "proceedings-article"})
_REVIEWED_SOURCES = frozenset({"journal", "conference"})


def abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str | None:
    """Rebuild the abstract text from OpenAlex's ``abstract_inverted_index`` (word -> positions)."""
    if not index or not isinstance(index, dict):
        return None
    slots: list[tuple[int, str]] = []
    for word, positions in index.items():
        if not isinstance(positions, list):
            continue
        slots.extend((p, word) for p in positions if isinstance(p, int))
    slots.sort()
    text = clean_text(" ".join(word for _, word in slots))
    return text or None


def _short_id(openalex_url: str | None) -> str | None:
    if not openalex_url or not isinstance(openalex_url, str):
        return None
    return openalex_url.rstrip("/").rsplit("/", 1)[-1] or None


def _type_hint(work: dict[str, Any]) -> str | None:
    for key in ("type", "type_crossref"):
        value = work.get(key)
        if isinstance(value, str) and value.lower() in _HINT_TYPES:
            return value.lower()
    return None


def _peer_reviewed(work: dict[str, Any], source_type: str | None) -> bool | None:
    """True only for journal or conference articles, False for preprints, else unknown."""
    if _type_hint(work) in ("preprint", "posted-content"):
        return False
    types = {str(work.get("type") or "").lower(), str(work.get("type_crossref") or "").lower()}
    if types & _REVIEWED_TYPES and (source_type or "").lower() in _REVIEWED_SOURCES:
        return True
    return None


def parse_work(work: dict[str, Any]) -> Study | None:
    """Convert one OpenAlex ``Work`` object into a Study, or None when it has no title."""
    title = clean_text(work.get("title") or work.get("display_name"))
    if not title:
        return None
    doi = normalize_doi(work.get("doi"))
    oa_id = _short_id(work.get("id"))
    if not doi and not oa_id:
        return None
    authors: list[str] = []
    for authorship in work.get("authorships") or []:
        name = format_author(((authorship or {}).get("author") or {}).get("display_name"))
        if name:
            authors.append(name)
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    venue = clean_text(source.get("display_name")) or None
    abstract = abstract_from_inverted_index(work.get("abstract_inverted_index"))
    year = work.get("publication_year")
    cited = work.get("cited_by_count")
    return Study(
        id=make_study_id(doi=doi, openalex_id=oa_id),
        title=title,
        authors=authors,
        year=year if isinstance(year, int) else None,
        venue=venue,
        doi=doi,
        url=f"https://doi.org/{doi}" if doi else (primary.get("landing_page_url") or work.get("id")),
        abstract=abstract,
        cited_by=cited if isinstance(cited, int) else None,
        design=classify_design(title, abstract, venue, work_type=_type_hint(work)),
        source="openalex",
        retracted=bool(work.get("is_retracted")),
        peer_reviewed=_peer_reviewed(work, source.get("type")),
    )


class OpenAlexClient:
    def __init__(self, fetcher: Fetcher, mailto: str | None = None, base_url: str = "https://api.openalex.org"):
        self.fetcher = fetcher
        self.mailto = mailto
        self.base_url = base_url.rstrip("/")

    def _url(self, path: str, params: dict[str, Any]) -> str:
        params = {k: v for k, v in params.items() if v not in (None, "")}
        if self.mailto:
            params["mailto"] = self.mailto            # polite pool
        return f"{self.base_url}{path}?{urlencode(params, quote_via=quote, safe=',:')}"

    def _get_json(self, url: str, *, allow_404: bool = False) -> dict[str, Any] | None:
        resp = self.fetcher.get(url, headers={"Accept": "application/json"})
        if allow_404 and resp.status == 404:
            return None
        if not resp.ok:
            raise ResearchApiError(f"openalex: HTTP {resp.status} for {url}")
        try:
            data = resp.json()
        except ValueError as err:
            raise ResearchApiError(f"openalex: response is not JSON ({err})") from err
        if not isinstance(data, dict):
            raise ResearchApiError("openalex: unexpected payload")
        return data

    def search(self, query: str, *, per_page: int = 10, year_from: int | None = None) -> list[Study]:
        if not query or not query.strip():
            return []                      # an empty search would list arbitrary works
        params: dict[str, Any] = {
            "search": query,
            "per-page": max(1, min(per_page, 200)),
            "select": SELECT_FIELDS,
        }
        if year_from is not None:
            params["filter"] = f"from_publication_date:{int(year_from)}-01-01"
        data = self._get_json(self._url("/works", params))
        results = (data or {}).get("results")
        if not isinstance(results, list):
            raise ResearchApiError("openalex: response has no results list")
        studies = (parse_work(w) for w in results if isinstance(w, dict))
        return [s for s in studies if s is not None]

    def by_doi(self, doi: str) -> Study | None:
        clean = normalize_doi(doi)
        if not clean:
            return None
        url = self._url(f"/works/doi:{quote(clean, safe='/')}", {"select": SELECT_FIELDS})
        data = self._get_json(url, allow_404=True)
        return parse_work(data) if data else None
