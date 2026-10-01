"""Shared helpers for the research tests: fixture loading and small payload builders.

All payloads follow the real response schemas of OpenAlex, Crossref and arXiv. Titles, authors and
DOIs in them are synthetic (DOI prefix 10.5555 is Crossref's test prefix).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from dopamine_king.research.models import Study

FIXTURES = Path(__file__).parent / "fixtures" / "research"

OPENALEX_SEARCH = "https://api.openalex.org/works?*"
OPENALEX_WORK = "https://api.openalex.org/works/*"
CROSSREF_SEARCH = "https://api.crossref.org/works?*"
CROSSREF_WORK = "https://api.crossref.org/works/*"
ARXIV_QUERY = "http://export.arxiv.org/api/query?*"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text("utf-8")


def fixture_json(name: str) -> Any:
    return json.loads(fixture_text(name))


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def make_study(
    title: str = "A Study",
    *,
    design: str = "observational",
    year: int | None = 2020,
    peer: bool | None = True,
    cited: int | None = None,
    doi: str | None = None,
    study_id: str | None = None,
    authors: list[str] | None = None,
    **kw: Any,
) -> Study:
    """Seed-like study with sensible defaults; the id follows the documented rule."""
    return Study(
        id=study_id or (f"doi:{doi}" if doi else f"seed:{slug(title)}"),
        title=title,
        authors=authors if authors is not None else ["Doe, J."],
        year=year,
        doi=doi,
        design=design,
        source=kw.pop("source", "seed"),
        peer_reviewed=peer,
        cited_by=cited,
        **kw,
    )


# --- OpenAlex ---------------------------------------------------------------------------


def oa_work(
    oa_id: str, title: str, *, doi: str | None = None, year: int | None = 2020, cited: int = 0,
    work_type: str = "article", retracted: bool = False, abstract: str | None = None,
    source_type: str | None = "journal",
) -> dict[str, Any]:
    index = None
    if abstract:
        index = {}
        for pos, word in enumerate(abstract.split()):
            index.setdefault(word, []).append(pos)
    return {
        "id": f"https://openalex.org/{oa_id}",
        "doi": f"https://doi.org/{doi}" if doi else None,
        "title": title,
        "display_name": title,
        "publication_year": year,
        "type": work_type,
        "type_crossref": "journal-article" if work_type == "article" else work_type,
        "cited_by_count": cited,
        "is_retracted": retracted,
        "abstract_inverted_index": index,
        "authorships": [{"author_position": "first", "author": {"display_name": "Jane Doe"}}],
        "primary_location": {"source": {"display_name": "Synthetic Journal", "type": source_type}}
        if source_type else None,
    }


def oa_payload(*works: dict[str, Any]) -> str:
    return json.dumps({"meta": {"count": len(works), "page": 1, "per_page": 10}, "results": list(works)})


# --- Crossref ---------------------------------------------------------------------------


def cr_item(
    doi: str, title: str, *, year: int | None = 2020, cited: int = 0, work_type: str = "journal-article",
    container: str | None = "Synthetic Journal", abstract: str | None = None, **extra: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "DOI": doi,
        "type": work_type,
        "title": [title],
        "author": [{"given": "Jane", "family": "Doe", "sequence": "first", "affiliation": []}],
        "is-referenced-by-count": cited,
    }
    if year is not None:
        item["issued"] = {"date-parts": [[year]]}
    if container:
        item["container-title"] = [container]
    if abstract:
        item["abstract"] = f"<jats:p>{abstract}</jats:p>"
    item.update(extra)
    return item


def cr_work_payload(item: dict[str, Any]) -> str:
    return json.dumps({"status": "ok", "message-type": "work", "message-version": "1.0.0", "message": item})


def cr_search_payload(*items: dict[str, Any]) -> str:
    return json.dumps({
        "status": "ok", "message-type": "work-list", "message-version": "1.0.0",
        "message": {"total-results": len(items), "items": list(items), "items-per-page": 10},
    })


# --- arXiv ------------------------------------------------------------------------------


def arxiv_entry(
    arxiv_id: str, title: str, *, year: int = 2020, doi: str | None = None, authors: tuple[str, ...] = ("Jane Doe",),
    summary: str = "A synthetic abstract.",
) -> str:
    people = "".join(f"<author><name>{a}</name></author>" for a in authors)
    doi_tag = f'<arxiv:doi xmlns:arxiv="http://arxiv.org/schemas/atom">{doi}</arxiv:doi>' if doi else ""
    return (
        f"<entry><id>http://arxiv.org/abs/{arxiv_id}v1</id><published>{year}-01-02T00:00:00Z</published>"
        f"<title>{title}</title><summary>{summary}</summary>{people}{doi_tag}</entry>"
    )


def arxiv_feed(*entries: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom">'
        "<title>ArXiv Query</title>" + "".join(entries) + "</feed>"
    )
