"""PubMed client (NCBI E-utilities): esearch for ids, esummary for the records.

Biomedical literature such as photobiomodulation lives in PubMed far more completely than in the
general scholarly indexes. No key is needed (about three requests per second); an ``api_key`` raises
the limit. All network access goes through the injected ``Fetcher``. PubMed publication types give a
much better design guess than title keywords, so they lead; anything not stated stays ``None``.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlencode

from ..net import Fetcher
from .grading import classify_design
from .models import (
    ResearchApiError, Study, clean_text, format_author_parts, make_study_id, normalize_doi,
)

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# First match wins. Publication types such as "Review" or "Journal Article" say too little, so the title decides.
_PUBTYPE_DESIGN = (
    ("Meta-Analysis", "meta-analysis"), ("Systematic Review", "systematic-review"),
    ("Randomized Controlled Trial", "rct"), ("Practice Guideline", "guideline"), ("Guideline", "guideline"),
    ("Consensus Development Conference", "guideline"), ("Observational Study", "observational"), ("Preprint", "preprint"),
)
_YEAR = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")


def _author(name: str | None) -> str | None:
    """"Vanin AA" -> "Vanin, A. A."; a name without trailing initials is kept as written."""
    name = clean_text(name)
    if not name:
        return None
    family, _, initials = name.rpartition(" ")
    if family and initials.isalpha() and initials.isupper() and len(initials) <= 4:
        return format_author_parts(initials, family)
    return name


def _doi(record: dict[str, Any]) -> str | None:
    for item in record.get("articleids") or []:
        if isinstance(item, dict) and item.get("idtype") == "doi":
            doi = normalize_doi(item.get("value"))
            if doi:
                return doi
    return normalize_doi(str(record.get("elocationid") or ""))


def parse_summary(record: dict[str, Any]) -> Study | None:
    """Convert one esummary record into a Study, or None when it has no title or id."""
    uid = str(record.get("uid") or "").strip()
    title = clean_text(record.get("title")).rstrip(".")
    if not uid or not title:
        return None
    pubtypes = [str(t) for t in record.get("pubtype") or []]
    design = next((d for t, d in _PUBTYPE_DESIGN if t in pubtypes), None)
    venue = clean_text(record.get("fulljournalname") or record.get("source")) or None
    year_match = _YEAR.search(str(record.get("pubdate") or record.get("epubdate") or ""))
    doi = _doi(record)
    cited = record.get("pmcrefcount")
    authors = [a for a in (_author((x or {}).get("name")) for x in record.get("authors") or [] if (x or {}).get("authtype", "Author") == "Author") if a]
    return Study(
        id=make_study_id(doi=doi, pmid=uid),
        title=title,
        authors=authors,
        year=int(year_match.group(1)) if year_match else None,
        venue=venue,
        doi=doi,
        url=f"https://doi.org/{doi}" if doi else f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
        abstract=None,                      # esummary carries no abstract; efetch would, at the cost of a second request
        cited_by=cited if isinstance(cited, int) else None,
        design=design or classify_design(title, None, venue),
        source="pubmed",
        retracted="Retracted Publication" in pubtypes,
        peer_reviewed=True if "Journal Article" in pubtypes else None,
    )


class PubMedClient:
    def __init__(self, fetcher: Fetcher, mailto: str | None = None, api_key: str | None = None, base_url: str = BASE_URL):
        self.fetcher = fetcher
        self.mailto = mailto
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _url(self, tool: str, params: dict[str, Any]) -> str:
        params = {k: v for k, v in params.items() if v not in (None, "")}
        params.update({"retmode": "json", "tool": "dopamine-king"})
        if self.mailto:
            params["email"] = self.mailto
        if self.api_key:
            params["api_key"] = self.api_key
        return f"{self.base_url}/{tool}.fcgi?{urlencode(params, quote_via=quote, safe=',:')}"

    def _get_json(self, url: str) -> dict[str, Any]:
        resp = self.fetcher.get(url, headers={"Accept": "application/json"})
        if not resp.ok:
            raise ResearchApiError(f"pubmed: HTTP {resp.status} for {url}")
        try:
            data = resp.json()
        except ValueError as err:
            raise ResearchApiError(f"pubmed: response is not JSON ({err})") from err
        if not isinstance(data, dict):
            raise ResearchApiError("pubmed: unexpected payload")
        return data

    def summaries(self, ids: list[str]) -> list[Study]:
        if not ids:
            return []
        data = self._get_json(self._url("esummary", {"db": "pubmed", "id": ",".join(ids)}))
        result = data.get("result")
        if not isinstance(result, dict):
            raise ResearchApiError("pubmed: esummary has no result object")
        studies = (parse_summary(result[i]) for i in ids if isinstance(result.get(i), dict))
        return [s for s in studies if s is not None]

    def search(self, query: str, *, retmax: int = 10, year_from: int | None = None) -> list[Study]:
        if not query or not query.strip():
            return []
        params: dict[str, Any] = {"db": "pubmed", "term": query.strip(), "retmax": max(1, min(retmax, 100)), "sort": "relevance"}
        if year_from is not None:
            params.update({"datetype": "pdat", "mindate": int(year_from), "maxdate": 3000})
        data = self._get_json(self._url("esearch", params))
        ids = ((data.get("esearchresult") or {}).get("idlist"))
        if not isinstance(ids, list):
            raise ResearchApiError("pubmed: esearch has no id list")
        return self.summaries([str(i) for i in ids])
